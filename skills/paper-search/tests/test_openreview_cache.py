"""Offline tests for the OpenReview SQLite cache (openreview_cache.py)."""

import openreview_cache as oc
import pytest
import search_papers_by_openreview as orx


@pytest.fixture()
def db(tmp_path):
    conn = oc.connect(tmp_path / "cache.sqlite3")
    yield conn
    conn.close()


def make_row(**overrides):
    row = {
        "id": "NOTE1",
        "venueid": "ICLR.cc/2025/Conference",
        "year": 2025,
        "number": 1,
        "title": "Prototypical Networks for Few-shot Learning",
        "abstract": "few-shot classification with class prototypes",
        "authors": '["Jake Snell"]',
        "cdate": 1735689600000,
        "publication_date": "2024-12-31",
        "venue": "ICLR 2025 poster",
        "decision": "ICLR 2025 poster",
        "publication_status": "accepted",
        "api_version": "v2",
        "provenance": "openreview-api",
        "fetched_at": "2026-09-07T00:00:00+00:00",
    }
    row.update(overrides)
    return row


def test_upsert_is_idempotent(db):
    assert oc.upsert_rows(db, [make_row()], overwrite=True) == 1
    db.commit()
    oc.upsert_rows(db, [make_row(title="Updated Title")], overwrite=True)
    db.commit()
    rows = db.execute("SELECT title FROM papers").fetchall()
    assert [row[0] for row in rows] == ["Updated Title"]


def test_seed_rows_never_overwrite_api_rows(db):
    oc.upsert_rows(db, [make_row(title="API Title")], overwrite=True)
    db.commit()
    seed_row = make_row(
        title="Seed Title",
        provenance=oc.SEED_PROVENANCE,
        publication_status="rejected",
    )
    oc.upsert_rows(db, [seed_row], overwrite=False)
    db.commit()
    title, provenance = db.execute(
        "SELECT title, provenance FROM papers WHERE id = 'NOTE1'"
    ).fetchone()
    assert (title, provenance) == ("API Title", "openreview-api")
    seed_only = make_row(
        id="SEEDONLY", provenance=oc.SEED_PROVENANCE, publication_status="rejected"
    )
    oc.upsert_rows(db, [seed_only], overwrite=False)
    db.commit()
    assert db.execute("SELECT count(*) FROM papers").fetchone()[0] == 2


def test_seed_decision_mapping():
    assert oc._status_from_seed_decision("Accept (Poster)") == "accepted"
    assert oc._status_from_seed_decision("Accept: notable-top-25%") == "accepted"
    assert oc._status_from_seed_decision("Reject") == "rejected"
    assert oc._status_from_seed_decision("Desk rejected") == "rejected"
    assert oc._status_from_seed_decision("Withdrawn") == "withdrawn"
    assert oc._status_from_seed_decision("") == "submitted"


def test_venue_year_targets_follow_measured_registry():
    targets = oc.venue_year_targets(2022, 2027, "v2")
    tmlr = [t for t in targets if t[0] == "TMLR"]
    assert tmlr == [("TMLR", None)]  # rolling venue appears exactly once, no year
    assert not any("CVPR" in v or "AAAI" in v or "aclweb.org" in v for v, _ in targets)
    assert ("ICLR.cc/2024/Conference", 2024) in targets
    assert not any(v == "ICLR.cc/2023/Conference" for v, _ in targets)
    assert ("NeurIPS.cc/2023/Conference", 2023) in targets
    assert not any(v == "NeurIPS.cc/2022/Conference" for v, _ in targets)
    v1 = oc.venue_year_targets(2021, 2023, "v1")
    assert set(v1) == {
        ("ICLR.cc/2021/Conference", 2021),
        ("ICLR.cc/2022/Conference", 2022),
        ("ICLR.cc/2023/Conference", 2023),
        ("NeurIPS.cc/2021/Conference", 2021),
        ("NeurIPS.cc/2022/Conference", 2022),
    }
    assert oc.venue_year_targets(2024, 2024, "v1") == []


def test_cache_search_ranks_and_matches_connector_schema(tmp_path, monkeypatch):
    conn = oc.connect(tmp_path / "cache.sqlite3")
    rows = [
        make_row(id="A", title="Diffusion policies for robot manipulation"),
        make_row(
            id="B",
            venueid="ICML.cc/2025/Conference",
            title="Unrelated paper about kernels",
            abstract="nothing to see",
        ),
    ]
    oc.upsert_rows(conn, rows, overwrite=True)
    conn.commit()
    conn.close()
    monkeypatch.setattr(oc, "DB_PATH", tmp_path / "cache.sqlite3")

    papers = oc.cache_search(["diffusion robot"], 2024, 2026, 5)
    assert [p["title"] for p in papers] == ["Diffusion policies for robot manipulation"]
    paper = papers[0]
    assert paper["url"] == "https://openreview.net/forum?id=A"
    assert paper["venue"] == "ICLR.cc/2025/Conference"
    assert paper["source"] == "openreview"
    assert paper["publication_status"] == "accepted"
    assert paper["citation_count"] is None
    assert paper["retrieval_ranks"][0]["source"] == "openreview"


def test_cache_search_filters_year_status_and_venues(tmp_path, monkeypatch):
    conn = oc.connect(tmp_path / "cache.sqlite3")
    oc.upsert_rows(
        conn,
        [
            make_row(id="IN", year=2025),
            make_row(id="OLD", year=2019),
            make_row(id="REJ", publication_status="rejected"),
        ],
        overwrite=True,
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(oc, "DB_PATH", tmp_path / "cache.sqlite3")

    papers = oc.cache_search(["prototypical"], 2024, 2026, 10)
    assert [p["url"] for p in papers] == ["https://openreview.net/forum?id=IN"]

    papers = oc.cache_search(
        ["prototypical"], 2024, 2026, 10, {"venues": ["NeurIPS.cc/2025/Conference"]}
    )
    assert papers == []


def test_cache_search_missing_db_raises_cache_unavailable(tmp_path):
    with pytest.raises(oc.CacheUnavailable):
        oc.cache_search(["anything"], 2024, 2026, 5, None, db_path=tmp_path / "nope")


def test_connector_cache_mode_strips_ranks_for_single_query(tmp_path, monkeypatch):
    conn = oc.connect(tmp_path / "cache.sqlite3")
    oc.upsert_rows(conn, [make_row()], overwrite=True)
    conn.commit()
    conn.close()
    monkeypatch.setattr(oc, "DB_PATH", tmp_path / "cache.sqlite3")

    papers = orx.search_papers_by_openreview(
        "few-shot classification", 2024, 2026, 5, source_options={"mode": "cache"}
    )
    assert len(papers) == 1
    assert "retrieval_ranks" not in papers[0]

    with pytest.raises(ValueError):
        orx.search_papers_by_openreview(
            "query", 2024, 2026, 5, source_options={"mode": "teleport"}
        )


def test_fts_match_expression_splits_on_separators():
    # unicode61 indexes "few-shot" as two tokens; the MATCH must split on
    # every non-token character (hyphen, quote, ...), not strip it.
    assert (
        oc._fts_match_expression(["few-shot", 'anti"quote'])
        == '"few" OR "shot" OR "anti" OR "quote"'
    )


def test_import_citations_fills_nulls_only(db, tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    oc.upsert_rows(
        db,
        [
            make_row(id="A"),
            make_row(id="B"),
        ],
        overwrite=True,
    )
    db.commit()
    db.close()

    crosswalk = tmp_path / "crosswalk.parquet"
    pq.write_table(
        pa.table(
            {
                "openreview_submission_id": ["A", "B"],
                "arxiv_id": ["2401.00001", None],
                "n_citations": [42, None],
            }
        ),
        crosswalk,
    )
    summary = oc.import_citations(crosswalk, tmp_path / "cache.sqlite3")
    assert summary["matched"] == 2
    assert summary["arxiv_filled"] == 1
    assert summary["citations_filled"] == 1

    # re-run must be a no-op (fills NULLs only, never clobbers)
    summary_again = oc.import_citations(crosswalk, tmp_path / "cache.sqlite3")
    assert summary_again["arxiv_filled"] == 0
    assert summary_again["citations_filled"] == 0

    papers = oc.cache_search(
        ["prototypical"], 2024, 2026, 5, db_path=tmp_path / "cache.sqlite3"
    )
    paper = papers[0]
    assert paper["arxiv_id"] == "2401.00001"
    assert paper["citation_count"] == 42
    assert paper["citation_source"] == "semantic_scholar"
