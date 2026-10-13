#!/usr/bin/env python3
"""Search OpenReview submissions through the documented venue/invitation API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from _env import load_env_once
from _http_runtime import configure_external_session
from postprocess import relevance_score, term_words

load_env_once()


_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "openreview_venues.json"
)

_CLIENT_CACHE: dict[str, object] = {}


def _error(diagnostics, query, error_type, message) -> None:
    print(f"[openreview] {error_type}: {message}", file=sys.stderr)
    if diagnostics is not None:
        diagnostics.append({"query": query, "type": error_type, "message": message})


def _exception_error(diagnostics, query, context, exc: Exception) -> None:
    _error(diagnostics, query, type(exc).__name__, f"{context}: {exc}")


def _content_value(content: dict, key: str, default=""):
    value = (content or {}).get(key, default)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _openreview_clients(use_v1: bool = False):
    """Create only the API client required by the selected venue mode."""
    cache_key = "v1" if use_v1 else "v2"
    if cache_key in _CLIENT_CACHE:
        return _CLIENT_CACHE[cache_key]
    try:
        import openreview
    except ImportError as exc:
        raise RuntimeError(
            "openreview not installed. pip install openreview-py"
        ) from exc

    username = os.environ.get("OPENREVIEW_USER") or os.environ.get(
        "OPENREVIEW_USERNAME", ""
    )
    password = os.environ.get("OPENREVIEW_PASS") or os.environ.get(
        "OPENREVIEW_PASSWORD", ""
    )
    if bool(username) != bool(password):
        raise RuntimeError(
            "OPENREVIEW_USER and OPENREVIEW_PASS must be provided together"
        )

    if use_v1:
        client = openreview.Client(baseurl="https://api.openreview.net")
    else:
        client = openreview.api.OpenReviewClient(baseurl="https://api2.openreview.net")
    configure_external_session(client.session, "openreview")
    if username:
        client.login_user(username=username, password=password)
    _CLIENT_CACHE[cache_key] = client
    return client


def _venue_year(venue_id: str) -> int | None:
    match = re.search(r"/(20\d{2})/", venue_id)
    return int(match.group(1)) if match else None


def _static_venues(
    start_year: int, end_year: int, api_version: str = "v2"
) -> list[str]:
    """Expand the maintained registry for a year range on one API version.

    Year-bearing venue ids are emitted once per matching year; year-less ids
    (the rolling TMLR) are emitted once whenever any year in the range matches.
    ``v2_from`` splits registry entries across the two OpenReview API versions.
    """
    try:
        payload = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        entries = payload["venues"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid OpenReview venue registry: {exc}") from exc

    venues = []
    seen = set()
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
            venue = str(entry["template"]).format(year=year)
            if venue in seen:
                continue
            seen.add(venue)
            venues.append(venue)
    return venues


def _resolve_submission_invitation(client, venue_id: str) -> str:
    """Resolve the submission invitation, tolerating non-standard venues.

    Most groups declare ``submission_name``; TMLR does not, so fall back to
    probing well-known invitation suffixes through ``get_invitation``.
    """
    group = client.get_group(venue_id)
    submission_name = _content_value(
        getattr(group, "content", {}) or {}, "submission_name", None
    )
    if submission_name:
        return f"{venue_id}/-/{submission_name}"
    for suffix in ("Submission", "Blind_Submission"):
        invitation = f"{venue_id}/-/{suffix}"
        try:
            client.get_invitation(invitation)
        except Exception as exc:
            _error(
                None, venue_id, "InvitationProbe", f"{invitation}: {type(exc).__name__}"
            )
            continue
        return invitation
    raise RuntimeError(
        f"venue {venue_id} has no submission_name and no known submission invitation"
    )


def _iter_notes(
    client,
    invitation: str,
    batch_size: int = 1000,
    content: dict | None = None,
):
    """Yield notes page by page using offset pagination.

    Offset paging (not the ``after`` cursor) is required on API v1: the cursor
    silently drops notes when many submissions share a creation timestamp
    (measured on NeurIPS 2022: cursor 1,605 notes vs 2,824 via offset).
    """
    offset = 0
    seen_ids: set[str] = set()
    while True:
        params = {"invitation": invitation, "limit": batch_size, "offset": offset}
        if content:
            params["content"] = content
        notes = client.get_notes(**params)
        if not notes:
            return
        for note in notes:
            note_id = str(getattr(note, "id", "") or "")
            if note_id and note_id in seen_ids:
                continue  # unstable server-side ordering; never yield twice
            if note_id:
                seen_ids.add(note_id)
            yield note
        if len(notes) < batch_size:
            return
        offset += batch_size


def _or_note_to_paper(note, venue: str, status_filter: str = "all") -> dict | None:
    content = getattr(note, "content", {}) or {}
    title = str(_content_value(content, "title", "") or "").strip()
    abstract = str(_content_value(content, "abstract", "") or "").strip()
    authors = _content_value(content, "authors", []) or []
    if isinstance(authors, str):
        authors = [authors]
    date_value = (
        getattr(note, "cdate", None)
        or getattr(note, "pdate", None)
        or getattr(note, "tcdate", None)
    )
    if not date_value:
        return None
    try:
        published = datetime.fromtimestamp(int(date_value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None
    note_id = str(getattr(note, "id", "") or "")
    if not title or not note_id:
        return None
    if status_filter == "accepted":
        publication_status = "accepted"
    else:
        venue_status = str(_content_value(content, "venueid", "") or "").casefold()
        if venue_status == venue.casefold():
            publication_status = "accepted"
        elif "withdraw" in venue_status:
            publication_status = "withdrawn"
        elif "reject" in venue_status:
            publication_status = "rejected"
        else:
            publication_status = "submitted"
    return {
        "title": title,
        "authors": list(authors),
        "year": _venue_year(venue) or published.year,
        "abstract": abstract,
        "url": f"https://openreview.net/forum?id={note_id}",
        "venue": venue,
        "citation_count": None,
        "citation_source": None,
        "publication_date": published.strftime("%Y-%m-%d"),
        "publication_status": publication_status,
        "status_source": "openreview",
        "source": "openreview",
        "doi": None,
        "arxiv_id": None,
    }


def _query_score(query: str, paper: dict) -> int:
    return relevance_score(paper, term_words([query]))


def _scan_venue(
    client,
    venue: str,
    start_year: int,
    end_year: int,
    status: str,
    scan_limit: int = 500,
    diagnostics: list[dict] | None = None,
    diagnostic_query: str | None = None,
) -> list[dict]:
    invitation = _resolve_submission_invitation(client, venue)
    content_filter = {"venueid": venue} if status == "accepted" else None
    found: list[dict] = []
    scanned = 0
    for note in _iter_notes(client, invitation, content=content_filter):
        scanned += 1
        paper = _or_note_to_paper(note, venue, status_filter=status)
        if paper is not None and start_year <= paper["year"] <= end_year:
            found.append(paper)
        if scanned >= scan_limit:
            _error(
                diagnostics,
                diagnostic_query,
                "CandidateScanTruncated",
                f"venue {venue} scan stopped after {scan_limit} submissions",
            )
            break
    return found


def _search_venue(
    client,
    venue: str,
    query: str,
    start_year: int,
    end_year: int,
    max_results: int,
    status: str,
    scan_limit: int = 500,
    diagnostics: list[dict] | None = None,
) -> list[dict]:
    found = []
    for paper in _scan_venue(
        client,
        venue,
        start_year,
        end_year,
        status,
        scan_limit,
        diagnostics,
        query,
    ):
        score = _query_score(query, paper)
        if score:
            paper["_openreview_score"] = score
            found.append(paper)
    found.sort(
        key=lambda paper: (
            -int(paper.get("_openreview_score", 0)),
            -int(paper.get("year") or 0),
            paper.get("title", "").casefold(),
        )
    )
    return found[:max_results]


def _prepare_search(
    query: str | None,
    start_year: int,
    end_year: int,
    max_results: int,
    venues: list[str] | None,
    diagnostics: list[dict] | None,
    source_options: dict | None,
):
    if max_results <= 0:
        return None
    options = source_options or {}
    explicit_venues = venues or options.get("venues")
    api_version = str(options.get("api_version", "v2")).lower()
    status = str(options.get("status", "accepted")).lower()
    scan_limit = options.get("scan_limit_per_venue", 500)
    if start_year > end_year:
        raise ValueError("OpenReview start_year must be <= end_year")
    if api_version not in {"v1", "v2"}:
        raise ValueError("OpenReview api_version must be 'v1' or 'v2'")
    if status not in {"accepted", "all"}:
        raise ValueError("OpenReview status must be 'accepted' or 'all'")
    if (
        not isinstance(scan_limit, int)
        or isinstance(scan_limit, bool)
        or scan_limit <= 0
    ):
        raise ValueError("OpenReview scan_limit_per_venue must be a positive integer")
    if explicit_venues is not None and (
        not isinstance(explicit_venues, (list, tuple))
        or not all(isinstance(venue, str) and venue for venue in explicit_venues)
    ):
        raise ValueError("OpenReview venues must be a non-empty list of venue IDs")
    if api_version == "v1" and not explicit_venues:
        raise ValueError("OpenReview v1 requires explicit venues")
    client = _openreview_clients(use_v1=api_version == "v1")
    selected_venues = list(explicit_venues or [])
    if not selected_venues:
        selected_venues = _static_venues(start_year, end_year, api_version)
    if not selected_venues:
        raise RuntimeError(
            f"OpenReview registry has no venues for {start_year}-{end_year}"
        )
    return client, selected_venues, status, scan_limit


def _cache_mode(source_options: dict | None) -> str:
    mode = str((source_options or {}).get("mode", "auto")).lower()
    if mode not in {"auto", "cache", "remote"}:
        raise ValueError("OpenReview mode must be 'auto', 'cache', or 'remote'")
    return mode


_CACHE_BUILD_HINT = (
    "build it with: uv run --no-project --with requests --with openreview-py "
    "scripts/openreview_cache.py build  (from the paper-search skill directory)"
)


def _try_cache(
    queries: list[str],
    start_year: int,
    end_year: int,
    max_results: int,
    source_options: dict | None,
    diagnostics: list[dict] | None,
    query_label: str | None,
) -> list[dict] | None:
    """Search the local SQLite cache; None means the cache is not usable."""
    mode = _cache_mode(source_options)
    if str((source_options or {}).get("status", "accepted")).lower() == "all":
        _error(
            diagnostics,
            query_label,
            "OpenReviewCacheSkipped",
            "cache serves accepted papers only; status=all uses the remote path",
        )
        return None
    try:
        import openreview_cache
    except ImportError as exc:
        message = f"cache module unavailable: {exc}"
        if mode == "cache":
            raise RuntimeError(f"{message}. {_CACHE_BUILD_HINT}") from exc
        _error(diagnostics, query_label, "OpenReviewCacheFallback", message)
        return None
    try:
        return openreview_cache.cache_search(
            queries, start_year, end_year, max_results, source_options
        )
    except openreview_cache.CacheUnavailable as exc:
        if mode == "cache":
            raise RuntimeError(
                f"OpenReview cache unavailable: {exc}. {_CACHE_BUILD_HINT}"
            ) from exc
        _error(diagnostics, query_label, "OpenReviewCacheFallback", str(exc))
        return None
    except Exception as exc:
        if mode == "cache":
            raise
        _error(
            diagnostics,
            query_label,
            "OpenReviewCacheFallback",
            f"{type(exc).__name__}: {exc}",
        )
        return None


def search_papers_by_openreview(
    query: str,
    start_year: int,
    end_year: int,
    max_results: int = 10,
    venues: list[str] | None = None,
    diagnostics: list[dict] | None = None,
    source_options: dict | None = None,
) -> list[dict]:
    """Search submissions through OpenReview.

    ``source_options.mode`` selects the path: ``cache`` answers from the local
    SQLite cache (see ``openreview_cache.py``), ``remote`` always hits the API,
    and the default ``auto`` uses the cache when it exists and is populated,
    falling back to the remote scan otherwise. Cache results are accepted-only;
    ``status=all`` forces the remote path.

    ``source_options`` supports ``venues``, ``api_version``,
    ``status`` (``accepted`` by default, or ``all``), ``scan_limit_per_venue``,
    and ``mode``.
    The default reads AI conference venues from the maintained registry.
    """
    if max_results <= 0:
        return []
    mode = _cache_mode(source_options)
    if mode != "remote":
        cached = _try_cache(
            [query],
            start_year,
            end_year,
            max_results,
            source_options,
            diagnostics,
            query,
        )
        if cached is not None:
            return [
                {k: v for k, v in paper.items() if k != "retrieval_ranks"}
                for paper in cached
            ]
    prepared = _prepare_search(
        query, start_year, end_year, max_results, venues, diagnostics, source_options
    )
    if prepared is None:
        return []
    client, selected_venues, status, scan_limit = prepared

    papers: list[dict] = []
    seen_ids: set[str] = set()
    # Keep enough candidates from every venue for the final global ranker. The
    # scan limit already bounds work, so a tiny per-venue cap only harms recall.
    per_venue_limit = max_results
    for venue in selected_venues:
        try:
            venue_papers = _search_venue(
                client,
                venue,
                query,
                start_year,
                end_year,
                per_venue_limit,
                status,
                scan_limit,
                diagnostics,
            )
        except Exception as exc:
            _exception_error(diagnostics, query, f"venue {venue} search failed", exc)
            continue
        for paper in venue_papers:
            if paper["url"] in seen_ids:
                continue
            seen_ids.add(paper["url"])
            papers.append(paper)
        time.sleep(0.2)
    papers.sort(
        key=lambda paper: (
            -int(paper.get("_openreview_score", 0)),
            -int(paper.get("year") or 0),
            paper.get("title", "").casefold(),
        )
    )
    for paper in papers:
        paper.pop("_openreview_score", None)
    return papers[:max_results]


def search_papers_by_openreview_queries(
    queries: list[str],
    start_year: int,
    end_year: int,
    max_results: int = 10,
    venues: list[str] | None = None,
    diagnostics: list[dict] | None = None,
    source_options: dict | None = None,
) -> list[dict]:
    """Search several queries while scanning each OpenReview venue only once.

    Honors ``mode`` (``auto``/``cache``/``remote``) exactly like
    :func:`search_papers_by_openreview`; the cache scans its FTS index once for
    all queries instead of once per venue.
    """
    clean_queries = [query.strip() for query in queries if query.strip()]
    if not clean_queries:
        raise ValueError("OpenReview queries must contain a non-empty string")
    mode = _cache_mode(source_options)
    if mode != "remote":
        cached = _try_cache(
            clean_queries,
            start_year,
            end_year,
            max_results,
            source_options,
            diagnostics,
            None,
        )
        if cached is not None:
            return cached
    prepared = _prepare_search(
        None, start_year, end_year, max_results, venues, diagnostics, source_options
    )
    if prepared is None:
        return []
    client, selected_venues, status, scan_limit = prepared

    candidates: dict[str, dict] = {}
    for venue in selected_venues:
        try:
            venue_papers = _scan_venue(
                client,
                venue,
                start_year,
                end_year,
                status,
                scan_limit,
                diagnostics,
            )
        except Exception as exc:
            _exception_error(diagnostics, None, f"venue {venue} search failed", exc)
            continue
        for paper in venue_papers:
            if any(_query_score(query, paper) for query in clean_queries):
                candidates.setdefault(paper["url"], paper)
        time.sleep(0.2)

    selected: dict[str, dict] = {}
    for query in clean_queries:
        scored = []
        for paper in candidates.values():
            score = _query_score(query, paper)
            if score:
                scored.append((paper, score))
        ranked = sorted(
            scored,
            key=lambda item: (
                -item[1],
                -int(item[0].get("year") or 0),
                item[0].get("title", "").casefold(),
            ),
        )[:max_results]
        for rank, (paper, _score) in enumerate(ranked, 1):
            result = selected.setdefault(paper["url"], dict(paper))
            result.setdefault("retrieval_ranks", []).append(
                {"query": query, "rank": rank, "source": "openreview"}
            )
    return list(selected.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--max-papers", type=int, default=10)
    parser.add_argument("--venues", nargs="*", default=None)
    parser.add_argument("--api-version", choices=("v1", "v2"), default="v2")
    parser.add_argument("--status", choices=("accepted", "all"), default="accepted")
    parser.add_argument("--scan-limit-per-venue", type=int, default=500)
    args = parser.parse_args()
    papers = search_papers_by_openreview(
        args.query,
        args.start_year,
        args.end_year,
        args.max_papers,
        venues=args.venues,
        source_options={
            "api_version": args.api_version,
            "status": args.status,
            "scan_limit_per_venue": args.scan_limit_per_venue,
        },
    )
    print(papers[0] if papers else "No papers found.")
