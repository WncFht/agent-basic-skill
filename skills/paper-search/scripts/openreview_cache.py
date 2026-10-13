#!/usr/bin/env python3
"""Local OpenReview accepted-paper cache (SQLite) for the paper-search skill.

One SQLite database holds every accepted submission of the registry's v2
venue-years plus the v1 NeurIPS backfill and the berenslab ICLR seed, so the
OpenReview connector can answer searches locally (mode=cache) instead of
scanning the live API.

Subcommands:
    build             First pull: API v2 accepted set (+v1 NeurIPS backfill) into the cache
    update            Probe unfrozen venue-years with one count request each; re-pull on change
    backfill-decisions Refresh rejected/withdrawn decisions (ICLR blind-submission rows)
    import-iclr-seed  Import the berenslab/iclr-dataset parquet (ICLR history incl. rejected)
    stats             Print per-venue cache coverage
    search            Run a cache query from the command line (debugging aid)

Run with: uv run --no-project --with requests --with openreview-py --with pyarrow \
    scripts/openreview_cache.py <command> ...
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from _env import load_env_once
from postprocess import relevance_score, term_words
from search_papers_by_openreview import (
    _REGISTRY_PATH,
    _content_value,
    _openreview_clients,
    _resolve_submission_invitation,
)

load_env_once()

_SKILL_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _SKILL_ROOT / "data" / "openreview_cache" / "openreview.sqlite3"
SEED_PROVENANCE = "berenslab/iclr-dataset@26v1"

# Politeness floor between upstream requests, enforced across processes like the
# arXiv throttle. OpenReview has no published rate limit; community measurements
# point to ~100 requests per rolling window with punitive lockouts past that.
_MIN_INTERVAL = float(os.environ.get("OPENREVIEW_MIN_INTERVAL", "0.5"))
_THROTTLE_FILE = os.path.join(tempfile.gettempdir(), "openreview_cache_throttle.lock")

_PAGE_SIZE = 1000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    venueid TEXT NOT NULL,
    year INTEGER NOT NULL,
    number INTEGER,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL DEFAULT '',
    authors TEXT NOT NULL DEFAULT '[]',
    cdate INTEGER,
    publication_date TEXT NOT NULL DEFAULT '',
    venue TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL DEFAULT '',
    publication_status TEXT NOT NULL DEFAULT 'accepted',
    api_version TEXT NOT NULL DEFAULT 'v2',
    provenance TEXT NOT NULL DEFAULT 'openreview-api',
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_venueid ON papers(venueid);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(publication_status);
CREATE TABLE IF NOT EXISTS venue_meta (
    venueid TEXT PRIMARY KEY,
    api_version TEXT NOT NULL,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    pulled_count INTEGER NOT NULL DEFAULT 0,
    frozen INTEGER NOT NULL DEFAULT 0,
    frozen_reason TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'openreview-api'
);
"""


class CacheUnavailable(RuntimeError):
    """Raised when cache mode is requested but the cache is missing or empty."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _throttle() -> None:
    """Block until >= _MIN_INTERVAL has elapsed since the last upstream request."""
    try:
        import fcntl as _fcntl
    except ImportError:
        time.sleep(_MIN_INTERVAL)
        return
    fd = os.open(_THROTTLE_FILE, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        _fcntl.flock(fd, _fcntl.LOCK_EX)
        raw = os.read(fd, 64).decode("utf-8").strip()
        try:
            last = float(raw) if raw else 0.0
        except ValueError:
            last = 0.0
        wait = _MIN_INTERVAL - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, str(time.time()).encode("utf-8"))
    finally:
        os.close(fd)


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (and create) the cache database with the full schema."""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(_SCHEMA)
    # Migrations for databases created before the citation prefill (TODO:
    # ALTER TABLE has no IF NOT EXISTS, hence the tolerance).
    for statement in (
        "ALTER TABLE papers ADD COLUMN arxiv_id TEXT",
        "ALTER TABLE papers ADD COLUMN citation_count INTEGER",
        "ALTER TABLE papers ADD COLUMN citation_source TEXT",
    ):
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass  # column already exists
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5("
            "title, abstract, content='papers', content_rowid='rowid', "
            "tokenize='porter unicode61')"
        )
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS papers_fts_ai AFTER INSERT ON papers BEGIN
                INSERT INTO papers_fts(rowid, title, abstract)
                VALUES (new.rowid, new.title, new.abstract);
            END;
            CREATE TRIGGER IF NOT EXISTS papers_fts_ad AFTER DELETE ON papers BEGIN
                INSERT INTO papers_fts(papers_fts, rowid, title, abstract)
                VALUES ('delete', old.rowid, old.title, old.abstract);
            END;
            CREATE TRIGGER IF NOT EXISTS papers_fts_au AFTER UPDATE ON papers BEGIN
                INSERT INTO papers_fts(papers_fts, rowid, title, abstract)
                VALUES ('delete', old.rowid, old.title, old.abstract);
                INSERT INTO papers_fts(rowid, title, abstract)
                VALUES (new.rowid, new.title, new.abstract);
            END;
            """
        )
    except sqlite3.OperationalError:
        pass  # FTS5 unavailable; cache_search degrades to LIKE
    return conn


def _operation_lock(db_path: Path | None = None):
    """Serialize whole build/update runs across processes (burst launches)."""
    path = (Path(db_path) if db_path else DB_PATH).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)

    class _Lock:
        def __enter__(self):
            self._fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
            fcntl.flock(self._fd, fcntl.LOCK_EX)

        def __exit__(self, *_exc):
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            return False

    return _Lock()


def venue_year_targets(
    start_year: int, end_year: int, api_version: str = "v2"
) -> list[tuple[str, int | None]]:
    """Expand the registry into (venueid, year-or-None) cache units.

    Year-bearing venues yield one unit per year; rolling venues (no year in the
    id, e.g. TMLR) yield a single unit so updates can re-probe them forever.
    """
    try:
        payload = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        entries = payload["venues"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid OpenReview venue registry: {exc}") from exc

    targets: list[tuple[str, int | None]] = []
    seen: set[str] = set()
    for year in range(start_year, end_year + 1):
        for entry in entries:
            if year < int(entry.get("min_year", 0)):
                continue
            v2_from = entry.get("v2_from")
            if v2_from is not None:
                if api_version == "v2" and year < int(v2_from):
                    continue
                if api_version == "v1" and year >= int(v2_from):
                    continue
            template = str(entry["template"])
            venue = template.format(year=year) if "{year}" in template else template
            if venue in seen:
                continue
            seen.add(venue)
            targets.append((venue, year if "{year}" in template else None))
    return targets


def _status_from_seed_decision(decision: str) -> str:
    text = (decision or "").strip().casefold()
    if text.startswith("accept"):
        return "accepted"
    if "withdraw" in text:
        return "withdrawn"
    if "reject" in text:
        return "rejected"
    return "submitted"


def _iso_date_from_ms(epoch_ms: int | None) -> str:
    if not epoch_ms:
        return ""
    try:
        return datetime.fromtimestamp(int(epoch_ms) / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _row_from_note(
    note, venueid: str, year: int | None, api_version: str, status: str = "accepted"
) -> dict:
    content = getattr(note, "content", {}) or {}
    title = str(_content_value(content, "title", "") or "").strip()
    if not title:
        return {}
    note_id = str(getattr(note, "id", "") or "")
    if not note_id:
        return {}
    cdate = getattr(note, "cdate", None) or getattr(note, "pdate", None)
    if year is None:
        iso = _iso_date_from_ms(cdate)
        year = int(iso[:4]) if iso else datetime.now(timezone.utc).year
    authors = _content_value(content, "authors", []) or []
    if isinstance(authors, str):
        authors = [authors]
    venue = str(_content_value(content, "venue", "") or "").strip()
    return {
        "id": note_id,
        "venueid": venueid,
        "year": int(year),
        "number": getattr(note, "number", None),
        "title": title,
        "abstract": str(_content_value(content, "abstract", "") or "").strip(),
        "authors": json.dumps([str(a) for a in authors], ensure_ascii=False),
        "cdate": int(cdate) if cdate else None,
        "publication_date": _iso_date_from_ms(cdate),
        "venue": venue,
        "decision": venue,
        "publication_status": status,
        "api_version": api_version,
        "provenance": "openreview-api",
        "fetched_at": _now(),
    }


# Seed rows must never clobber API-pulled rows (INSERT OR IGNORE), and the
# seed itself contains duplicate OpenReview ids, so plain INSERT is not safe.
_INSERT_ROW = """
INSERT OR IGNORE INTO papers (id, venueid, year, number, title, abstract, authors, cdate,
                             publication_date, venue, decision, publication_status,
                             api_version, provenance, fetched_at)
VALUES (:id, :venueid, :year, :number, :title, :abstract, :authors, :cdate,
        :publication_date, :venue, :decision, :publication_status,
        :api_version, :provenance, :fetched_at)
"""

_UPSERT_ROW = (
    _INSERT_ROW
    + """
ON CONFLICT(id) DO UPDATE SET
    venueid=excluded.venueid, year=excluded.year, number=excluded.number,
    title=excluded.title, abstract=excluded.abstract, authors=excluded.authors,
    cdate=excluded.cdate, publication_date=excluded.publication_date,
    venue=excluded.venue, decision=excluded.decision,
    publication_status=excluded.publication_status, api_version=excluded.api_version,
    provenance=excluded.provenance, fetched_at=excluded.fetched_at
"""
)


def upsert_rows(conn: sqlite3.Connection, rows: list[dict], overwrite: bool) -> int:
    """Insert API-pulled (overwrite) or seed (first-write-wins) rows."""
    if not rows:
        return 0
    conn.executemany(_UPSERT_ROW if overwrite else _INSERT_ROW, rows)
    return len(rows)


def set_meta(
    conn: sqlite3.Connection,
    venueid: str,
    api_version: str,
    accepted_count: int,
    pulled_count: int,
    frozen: bool,
    frozen_reason: str = "",
    source: str = "openreview-api",
) -> None:
    conn.execute(
        """
        INSERT INTO venue_meta (venueid, api_version, accepted_count, pulled_count,
                                frozen, frozen_reason, fetched_at, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(venueid) DO UPDATE SET
            api_version=excluded.api_version,
            accepted_count=excluded.accepted_count,
            pulled_count=excluded.pulled_count,
            frozen=excluded.frozen,
            frozen_reason=excluded.frozen_reason,
            fetched_at=excluded.fetched_at,
            source=excluded.source
        """,
        (
            venueid,
            api_version,
            accepted_count,
            pulled_count,
            int(frozen),
            frozen_reason,
            _now(),
            source,
        ),
    )


def get_meta(conn: sqlite3.Connection, venueid: str) -> dict | None:
    row = conn.execute(
        "SELECT venueid, api_version, accepted_count, pulled_count, frozen,"
        " frozen_reason, fetched_at, source FROM venue_meta WHERE venueid = ?",
        (venueid,),
    ).fetchone()
    if row is None:
        return None
    keys = (
        "venueid",
        "api_version",
        "accepted_count",
        "pulled_count",
        "frozen",
        "frozen_reason",
        "fetched_at",
        "source",
    )
    return dict(zip(keys, row))


def _invitation_for(client, venueid: str, api_version: str) -> str:
    """Resolve the submission invitation.

    v2 resolution (including the TMLR-style fallback) lives in the connector's
    ``_resolve_submission_invitation``. v1 groups rarely declare the name at
    all, so probe the known suffixes by note existence.
    """
    if api_version == "v2":
        return _resolve_submission_invitation(client, venueid)
    for suffix in ("Blind_Submission", "Submission"):
        invitation = f"{venueid}/-/{suffix}"
        _throttle()
        try:
            if client.get_notes(invitation=invitation, limit=1):
                return invitation
        except Exception as exc:
            print(
                f"  invitation probe {invitation}: {type(exc).__name__}",
                file=sys.stderr,
            )
    raise RuntimeError(f"no submission invitation found for {venueid}")


def _pull_venue_year(
    conn: sqlite3.Connection,
    client,
    venueid: str,
    year: int | None,
    api_version: str,
    *,
    expected_count: int | None = None,
) -> tuple[int, int | None]:
    """Pull one venue-year's accepted set with offset paging; upsert rows."""
    invitation = _invitation_for(client, venueid, api_version)
    content = {"venueid": venueid}
    rows: list[dict] = []
    offset = 0
    while True:
        _throttle()
        # openreview-py only returns (notes, count) from with_count when offset
        # is absent, so the count is fetched on the first page only.
        params = {"invitation": invitation, "content": content, "limit": _PAGE_SIZE}
        if offset:
            params["offset"] = offset
        if api_version == "v2" and offset == 0:
            notes, total = client.get_notes(**params, with_count=True)
            if expected_count is None:
                expected_count = total
        else:
            notes = client.get_notes(**params)
            total = None
        if not notes:
            break
        for note in notes:
            row = _row_from_note(note, venueid, year, api_version)
            if row:
                rows.append(row)
        if len(notes) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    pulled = upsert_rows(conn, rows, overwrite=True)
    frozen = year is not None and year < datetime.now(timezone.utc).year
    set_meta(
        conn,
        venueid,
        api_version,
        accepted_count=expected_count if expected_count is not None else len(rows),
        pulled_count=pulled,
        frozen=frozen,
        frozen_reason="year completed"
        if frozen
        else ("rolling" if year is None else ""),
    )
    return pulled, expected_count


def _probe_venue_year(client, venueid: str, year: int | None, api_version: str) -> int:
    """One cheap request: the venue-year's current accepted count."""
    if api_version != "v2":
        raise RuntimeError("count probe is only implemented for API v2")
    invitation = _invitation_for(client, venueid, api_version)
    _throttle()
    _notes, count = client.get_notes(
        invitation=invitation,
        content={"venueid": venueid},
        limit=1,
        with_count=True,
    )
    return int(count)


def build_cache(
    db_path: Path | None = None,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
) -> dict:
    """First pull: every v2 venue-year in range + the v1 NeurIPS backfill."""
    end = end_year or datetime.now(timezone.utc).year
    start = start_year or 2022  # earliest v2 registry entry (TMLR)
    summary: dict = {"pulled": {}, "skipped": [], "errors": []}
    with _operation_lock(db_path):
        conn = connect(db_path)
        try:
            client_v2 = _openreview_clients(use_v1=False)
            client_v1 = _openreview_clients(use_v1=True)
            targets = venue_year_targets(start, end, "v2")
            # NeurIPS 2021-2022 accepted live on API v1; ICLR 2021-2023 comes
            # from the seed import instead (its venueid semantics differ).
            targets += [
                ("NeurIPS.cc/2021/Conference", 2021),
                ("NeurIPS.cc/2022/Conference", 2022),
            ]
            for venueid, year in targets:
                api_version = (
                    "v1"
                    if (year in (2021, 2022) and venueid.startswith("NeurIPS.cc/"))
                    else "v2"
                )
                client = client_v1 if api_version == "v1" else client_v2
                meta = get_meta(conn, venueid)
                if (
                    meta is not None
                    and meta["pulled_count"] > 0
                    and year is not None
                    and year < datetime.now(timezone.utc).year
                ):
                    summary["skipped"].append(venueid)
                    continue  # frozen year already cached; API rows never change
                try:
                    pulled, count = _pull_venue_year(
                        conn, client, venueid, year, api_version
                    )
                    summary["pulled"][venueid] = {"rows": pulled, "count": count}
                    print(
                        f"  pulled {venueid}: {pulled} rows (count={count})",
                        file=sys.stderr,
                    )
                except Exception as exc:
                    summary["errors"].append(
                        {
                            "venueid": venueid,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    print(
                        f"  ERROR {venueid}: {type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )
            conn.commit()
        finally:
            conn.close()
    return summary


def update_cache(
    db_path: Path | None = None,
    *,
    end_year: int | None = None,
    start_year: int | None = None,
) -> dict:
    """Probe unfrozen venue-years (1 request each); re-pull only on drift."""
    end = end_year or datetime.now(timezone.utc).year
    start = start_year or 2022
    summary: dict = {"unchanged": [], "refreshed": {}, "missing": [], "errors": []}
    with _operation_lock(db_path):
        conn = connect(db_path)
        try:
            client = _openreview_clients(use_v1=False)
            for venueid, year in venue_year_targets(start, end, "v2"):
                meta = get_meta(conn, venueid)
                frozen = year is not None and year < datetime.now(timezone.utc).year
                if frozen and meta is not None:
                    continue  # decision done, cached, never changes
                if frozen and meta is None:
                    # Frozen year never pulled (e.g. venue appeared after build):
                    # a full pull is the only way to fill it.
                    try:
                        pulled, count = _pull_venue_year(
                            conn, client, venueid, year, "v2"
                        )
                        summary["refreshed"][venueid] = {"rows": pulled, "count": count}
                    except Exception as exc:
                        summary["errors"].append(
                            {
                                "venueid": venueid,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                    continue
                try:
                    count = _probe_venue_year(client, venueid, year, "v2")
                except Exception as exc:
                    # Venue not announced yet (missing group/invitation): treat as 0
                    message = str(exc)
                    if "NotFound" in message or "not found" in message.casefold():
                        set_meta(
                            conn,
                            venueid,
                            "v2",
                            0,
                            0,
                            frozen=False,
                            frozen_reason="venue not announced yet",
                        )
                        summary["missing"].append(venueid)
                        continue
                    summary["errors"].append(
                        {"venueid": venueid, "error": f"{type(exc).__name__}: {exc}"}
                    )
                    continue
                if meta is not None and meta["accepted_count"] == count:
                    summary["unchanged"].append(venueid)
                    continue
                pulled, _ = _pull_venue_year(
                    conn, client, venueid, year, "v2", expected_count=count
                )
                summary["refreshed"][venueid] = {"rows": pulled, "count": count}
            conn.commit()
        finally:
            conn.close()
    return summary


# Non-accepted submissions are re-labelled under NESTED venueids
# ({venueid}/Rejected_Submission) while keeping their original note id; query
# them through the main submission invitation. The sibling form
# ({prefix}/{year}/Rejected_Submission) returns 0 - measured, don't "fix" it.
_DECISION_POOLS = (
    ("Rejected_Submission", "rejected"),
    ("Withdrawn_Submission", "withdrawn"),
    ("Desk_Rejected_Submission", "rejected"),
)


def backfill_decisions(
    db_path: Path | None = None,
    *,
    venue_years: list[tuple[str, int]] | None = None,
) -> dict:
    """Refresh decisions for non-accepted rows (e.g. ICLR blind submissions).

    Decision-day venues re-label notes under nested venueids; pulling those
    pools and upserting by note id turns the seed's status-less blind rows
    into a decided dataset. Accepted rows come from build/update, not here.
    """
    if venue_years is None:
        venue_years = [
            (f"ICLR.cc/{year}/Conference", year) for year in (2024, 2025, 2026)
        ]
    summary: dict = {"pools": {}, "errors": []}
    with _operation_lock(db_path):
        conn = connect(db_path)
        try:
            client = _openreview_clients(use_v1=False)
            for venueid, year in venue_years:
                invitation = _invitation_for(client, venueid, "v2")
                for suffix, status in _DECISION_POOLS:
                    nested = f"{venueid}/{suffix}"
                    rows: list[dict] = []
                    offset = 0
                    count = None
                    while True:
                        _throttle()
                        # with_count only pairs with an absent offset; fetch the
                        # pool size on the first page like _pull_venue_year.
                        params = {
                            "invitation": invitation,
                            "content": {"venueid": nested},
                            "limit": _PAGE_SIZE,
                        }
                        if offset:
                            params["offset"] = offset
                        if offset == 0:
                            notes, count = client.get_notes(**params, with_count=True)
                        else:
                            notes = client.get_notes(**params)
                        if not notes:
                            break
                        for note in notes:
                            row = _row_from_note(
                                note, venueid, year, "v2", status=status
                            )
                            if row:
                                rows.append(row)
                        if len(notes) < _PAGE_SIZE:
                            break
                        offset += _PAGE_SIZE
                    upsert_rows(conn, rows, overwrite=True)
                    summary["pools"][nested] = len(rows)
                    print(
                        f"  {nested}: {len(rows)} rows (count={count})",
                        file=sys.stderr,
                    )
            conn.commit()
        finally:
            conn.close()
    return summary


def import_iclr_seed(
    parquet_path: Path,
    db_path: Path | None = None,
    *,
    provenance: str = SEED_PROVENANCE,
) -> dict:
    """Import the berenslab/iclr-dataset parquet without clobbering API rows."""
    import pyarrow.parquet as pq

    summary: dict = {"rows_read": 0, "imported": 0, "by_year": {}}
    table = pq.read_table(str(parquet_path))
    columns = {name: table.column(name).to_pylist() for name in table.column_names}
    required = {"year", "id", "title", "abstract", "authors", "decision"}
    missing = required - set(columns)
    if missing:
        raise RuntimeError(f"seed parquet missing columns: {sorted(missing)}")

    with _operation_lock(db_path):
        conn = connect(db_path)
        try:
            rows_before = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
            now = _now()
            batch: list[dict] = []
            seen_ids: set[str] = set()
            for index in range(table.num_rows):
                summary["rows_read"] += 1
                title = str(columns["title"][index] or "").strip()
                if not title:
                    continue
                year = int(columns["year"][index])
                note_id = str(columns["id"][index] or "").strip()
                if not note_id:
                    seed_hash = hashlib.sha1(f"{title}|{year}".encode()).hexdigest()[
                        :16
                    ]
                    note_id = f"seed-{seed_hash}"
                if note_id in seen_ids:
                    summary["duplicate_ids"] = summary.get("duplicate_ids", 0) + 1
                    continue
                seen_ids.add(note_id)
                decision = str(columns["decision"][index] or "").strip()
                status = _status_from_seed_decision(decision)
                authors_raw = str(columns["authors"][index] or "")
                authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
                cdate = columns["cdate"][index] if "cdate" in columns else None
                batch.append(
                    {
                        "id": note_id,
                        "venueid": f"ICLR.cc/{year}/Conference",
                        "year": year,
                        "number": None,
                        "title": title,
                        "abstract": str(columns["abstract"][index] or "").strip(),
                        "authors": json.dumps(authors, ensure_ascii=False),
                        "cdate": int(cdate) if cdate else None,
                        "publication_date": _iso_date_from_ms(cdate),
                        "venue": "ICLR",
                        "decision": decision,
                        "publication_status": status,
                        "api_version": "v1" if year <= 2023 else "v2",
                        "provenance": provenance,
                        "fetched_at": now,
                    }
                )
                if len(batch) >= 5000:
                    summary["imported"] += upsert_rows(conn, batch, overwrite=False)
                    batch = []
            summary["imported"] += upsert_rows(conn, batch, overwrite=False)
            rows_after = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
            summary["newly_inserted"] = rows_after - rows_before

            # Frozen per-year meta for the v1-era ICLR years the seed owns.
            per_year: dict[str, dict[str, int]] = {}
            conn.commit()
            for venueid, year_value, status, count in conn.execute(
                "SELECT venueid, year, publication_status, count(*) FROM papers "
                "WHERE provenance LIKE 'berenslab%' GROUP BY venueid, year, publication_status"
            ):
                per_year.setdefault(venueid, {})[status] = count
            for venueid, statuses in per_year.items():
                year_value = int(venueid.split("/")[1])
                if year_value > 2023:
                    continue  # API owns ICLR 2024+; no seed meta rows
                set_meta(
                    conn,
                    venueid,
                    "v1",
                    accepted_count=statuses.get("accepted", 0),
                    pulled_count=sum(statuses.values()),
                    frozen=True,
                    frozen_reason="seed import (frozen history)",
                    source=provenance,
                )
                summary["by_year"][venueid] = statuses
            conn.commit()
        finally:
            conn.close()
    return summary


def import_citations(
    crosswalk_parquet: Path,
    db_path: Path | None = None,
) -> dict:
    """Prefill arxiv_id / citation_count from an S2-enriched crosswalk.

    Expects a parquet with ``openreview_submission_id`` and optional
    ``title``, ``arxiv_id``, ``n_citations`` (the nhop/OpenReview slim
    extract; see README). Fills NULLs only, so it never clobbers OpenAlex
    enrichment and is safe to re-run. Source data is CC-BY-NC: local
    research use.
    """
    import pyarrow.parquet as pq

    table = pq.read_table(str(crosswalk_parquet))
    columns = {name: table.column(name).to_pylist() for name in table.column_names}
    if "openreview_submission_id" not in columns:
        raise RuntimeError("crosswalk parquet lacks openreview_submission_id")

    summary: dict = {
        "crosswalk_rows": 0,
        "matched": 0,
        "arxiv_filled": 0,
        "citations_filled": 0,
    }
    with _operation_lock(db_path):
        conn = connect(db_path)
        try:
            lookup: dict[str, tuple[str | None, int | None]] = {}
            for index in range(table.num_rows):
                note_id = str(columns["openreview_submission_id"][index] or "").strip()
                if not note_id:
                    continue
                summary["crosswalk_rows"] += 1
                arxiv = str(columns["arxiv_id"][index] or "").strip() or None
                citations = columns["n_citations"][index]
                citations = int(citations) if citations is not None else None
                lookup[note_id] = (arxiv, citations)

            updates: list[tuple] = []
            for note_id, arxiv_id, citation_count in conn.execute(
                "SELECT id, arxiv_id, citation_count FROM papers"
            ):
                if note_id not in lookup:
                    continue
                source_arxiv, source_citations = lookup[note_id]
                summary["matched"] += 1
                new_arxiv = arxiv_id if arxiv_id else source_arxiv
                new_citations = (
                    citation_count if citation_count is not None else source_citations
                )
                if new_arxiv != arxiv_id or new_citations != citation_count:
                    updates.append(
                        (
                            new_arxiv,
                            new_citations,
                            "semantic_scholar" if new_citations is not None else None,
                            note_id,
                        )
                    )
                    if arxiv_id is None and new_arxiv:
                        summary["arxiv_filled"] += 1
                    if citation_count is None and new_citations is not None:
                        summary["citations_filled"] += 1
            conn.executemany(
                "UPDATE papers SET arxiv_id = ?, citation_count = ?,"
                " citation_source = ? WHERE id = ?",
                updates,
            )
            conn.commit()
        finally:
            conn.close()
    return summary


def export_snapshot(db_path: Path | None = None, out_path: Path | None = None) -> Path:
    """Write a compact, diffable CSV index of the cache into git.

    The SQLite database is gitignored (rebuildable), so this snapshot is the
    disaster-recovery floor AND the change log: per-venue-year row/decision
    diffs after every update make upstream convention changes visible.
    """
    import csv

    path = out_path or (_SKILL_ROOT / "data" / "openreview_cache_snapshot.csv")
    source = Path(db_path) if db_path else DB_PATH
    if not source.exists():
        raise CacheUnavailable(f"cache database missing at {source}")
    conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT id, venueid, year, publication_status, decision, title"
            " FROM papers ORDER BY venueid, year, id"
        )
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "venueid", "year", "status", "decision", "title"])
            writer.writerows(rows)
    finally:
        conn.close()
    return path


def print_stats(db_path: Path | None = None) -> None:
    path = Path(db_path) if db_path else DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
    print(f"db: {path}")
    print(f"papers total: {total}")
    print(
        f"{'venueid':44s} {'rows':>6s} {'accepted':>8s} {'frozen':>6s} "
        f"{'source':24s} {'fetched_at':20s}"
    )
    rows = conn.execute(
        "SELECT m.venueid, m.api_version, m.accepted_count, m.pulled_count, m.frozen,"
        " m.fetched_at, m.source,"
        " (SELECT count(*) FROM papers p WHERE p.venueid = m.venueid) AS n_rows,"
        " (SELECT count(*) FROM papers p WHERE p.venueid = m.venueid"
        "  AND p.publication_status = 'accepted') AS n_accepted"
        " FROM venue_meta m ORDER BY m.venueid"
    ).fetchall()
    for row in rows:
        print(
            f"{row['venueid']:44s} {row['n_rows']:6d} {row['n_accepted']:8d} "
            f"{'yes' if row['frozen'] else 'no':>6s} {row['source']:24s} "
            f"{row['fetched_at'][:19]:20s}"
        )
    orphans = conn.execute(
        "SELECT venueid, count(*) FROM papers WHERE venueid NOT IN"
        " (SELECT venueid FROM venue_meta) GROUP BY venueid"
    ).fetchall()
    if orphans:
        print("rows without venue_meta:")
        for venueid, count in orphans:
            print(f"  {venueid}: {count}")
    conn.close()


def _fts_match_expression(terms: list[str]) -> str:
    """Build an OR-of-quoted-tokens MATCH expression.

    Non-alphanumeric runs must SPLIT terms, not be stripped: the unicode61
    tokenizer indexes "few-shot" as "few" and "shot", so a MATCH for the
    stripped "fewshot" would silently recall nothing.
    """
    fragments: list[str] = []
    for term in terms:
        for piece in re.split(r"[^a-z0-9_]+", term.casefold()):
            if piece and piece not in fragments:
                fragments.append(piece)
    return " OR ".join(f'"{piece}"' for piece in fragments)


def cache_search(
    queries: list[str],
    start_year: int,
    end_year: int,
    max_results: int,
    source_options: dict | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """Search the local cache; mirror the remote connector's contract.

    Returns papers shaped like ``search_papers_by_openreview_queries`` output
    (including ``retrieval_ranks``). Raises ``CacheUnavailable`` when the cache
    is missing or empty so the connector can fall back to the remote path.
    """
    path = Path(db_path) if db_path else DB_PATH
    if not path.exists():
        raise CacheUnavailable(f"cache database missing at {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
        if total == 0:
            raise CacheUnavailable(f"cache database at {path} is empty")
        has_fts = bool(
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='papers_fts'"
            ).fetchone()
        )

        options = source_options or {}
        venues = options.get("venues") or None
        clean_queries = [q.strip() for q in queries if q.strip()]
        if not clean_queries:
            return []
        terms: list[str] = []
        for query in term_words(clean_queries):
            if query not in terms:
                terms.append(query)

        params: list = []
        where = ["p.publication_status = 'accepted'"]
        if has_fts:
            match = _fts_match_expression(terms)
            if not match:
                return []
            from_clause = "papers p JOIN papers_fts ON papers_fts.rowid = p.rowid"
            where.append("papers_fts MATCH ?")
            params.append(match)
        else:
            from_clause = "papers p"
            clauses = []
            for term in terms:
                clauses.append("(p.title LIKE ? OR p.abstract LIKE ?)")
                like = f"%{term}%"
                params.extend([like, like])
            where.append("(" + " OR ".join(clauses) + ")")
        where.append("p.year BETWEEN ? AND ?")
        params.extend([start_year, end_year])
        if venues:
            placeholders = ",".join("?" for _ in venues)
            where.append(f"p.venueid IN ({placeholders})")
            params.extend(venues)

        sql = (
            f"SELECT p.* FROM {from_clause} WHERE "
            + " AND ".join(where)
            + " LIMIT 20000"
        )
        candidates: dict[str, dict] = {}
        for row in conn.execute(sql, params):
            paper = {
                "title": row["title"],
                "authors": json.loads(row["authors"] or "[]"),
                "year": row["year"],
                "abstract": row["abstract"],
                "url": f"https://openreview.net/forum?id={row['id']}",
                "venue": row["venueid"],
                "citation_count": row["citation_count"],
                "citation_source": row["citation_source"],
                "publication_date": row["publication_date"],
                "publication_status": row["publication_status"],
                "status_source": "openreview",
                "source": "openreview",
                "doi": None,
                "arxiv_id": row["arxiv_id"],
            }
            candidates[paper["url"]] = paper

        selected: dict[str, dict] = {}
        for query in clean_queries:
            query_terms = term_words([query])
            scored = []
            for paper in candidates.values():
                score = relevance_score(paper, query_terms)
                if score:
                    scored.append((paper, score))
            scored.sort(
                key=lambda item: (
                    -item[1],
                    -int(item[0].get("year") or 0),
                    item[0].get("title", "").casefold(),
                )
            )
            for rank, (paper, _score) in enumerate(scored[:max_results], 1):
                result = selected.setdefault(paper["url"], dict(paper))
                result.setdefault("retrieval_ranks", []).append(
                    {"query": query, "rank": rank, "source": "openreview"}
                )
        return list(selected.values())
    finally:
        conn.close()


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="first pull into the cache")
    build.add_argument("--start-year", type=int, default=2022)
    build.add_argument("--end-year", type=int, default=None)
    build.add_argument("--db", type=Path, default=None)

    update = sub.add_parser("update", help="probe and re-pull drifted venue-years")
    update.add_argument("--start-year", type=int, default=2022)
    update.add_argument("--end-year", type=int, default=None)
    update.add_argument("--db", type=Path, default=None)

    backfill = sub.add_parser(
        "backfill-decisions",
        help="refresh rejected/withdrawn decisions (ICLR 2024-2026 by default)",
    )
    backfill.add_argument("--db", type=Path, default=None)

    seed = sub.add_parser("import-iclr-seed", help="import berenslab ICLR parquet")
    seed.add_argument("parquet", type=Path)
    seed.add_argument("--db", type=Path, default=None)

    citations = sub.add_parser(
        "import-citations",
        help="prefill arxiv_id/citations from an S2 crosswalk parquet (fills NULLs)",
    )
    citations.add_argument("parquet", type=Path)
    citations.add_argument("--db", type=Path, default=None)

    stats = sub.add_parser("stats", help="print per-venue coverage")
    stats.add_argument("--db", type=Path, default=None)

    snapshot = sub.add_parser(
        "export-snapshot", help="write the diffable CSV index into git"
    )
    snapshot.add_argument("--db", type=Path, default=None)
    snapshot.add_argument("--out", type=Path, default=None)

    search = sub.add_parser("search", help="query the cache (debugging aid)")
    search.add_argument("query")
    search.add_argument("--start-year", type=int, default=2022)
    search.add_argument("--end-year", type=int, default=None)
    search.add_argument("--max-papers", type=int, default=10)
    search.add_argument("--db", type=Path, default=None)

    args = parser.parse_args()
    if args.command == "build":
        summary = build_cache(
            args.db,
            start_year=args.start_year,
            end_year=args.end_year,
        )
        print(json.dumps(summary, indent=1, default=str))
    elif args.command == "update":
        summary = update_cache(
            args.db, start_year=args.start_year, end_year=args.end_year
        )
        print(json.dumps(summary, indent=1, default=str))
    elif args.command == "backfill-decisions":
        summary = backfill_decisions(args.db)
        print(json.dumps(summary, indent=1, default=str))
    elif args.command == "import-iclr-seed":
        summary = import_iclr_seed(args.parquet, args.db)
        print(json.dumps(summary, indent=1, default=str))
    elif args.command == "import-citations":
        summary = import_citations(args.parquet, args.db)
        print(json.dumps(summary, indent=1, default=str))
    elif args.command == "stats":
        print_stats(args.db)
    elif args.command == "export-snapshot":
        written = export_snapshot(args.db, args.out)
        print(f"snapshot written: {written}")
    elif args.command == "search":
        end = args.end_year or datetime.now(timezone.utc).year
        papers = cache_search(
            [args.query],
            args.start_year,
            end,
            args.max_papers,
            None,
            db_path=args.db,
        )
        for paper in papers:
            print(f"[{paper['year']}] {paper['title']}  ({paper['venue']})")
        print(f"{len(papers)} result(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
