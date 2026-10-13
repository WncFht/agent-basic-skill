from postprocess import dedup, rank


def paper(source, title, **overrides):
    record = {
        "source": source,
        "title": title,
        "authors": ["Ada Lovelace"],
        "year": 2025,
        "abstract": "",
        "url": "",
        "venue": "",
        "citation_count": None,
        "citation_source": None,
        "publication_date": "2025-01-01",
        "date_precision": "day",
        "publication_status": "published",
        "status_source": source,
        "doi": None,
        "arxiv_id": None,
    }
    record.update(overrides)
    return record


def test_conflicting_dois_with_same_title_stay_separate():
    merged = dedup(
        {
            "semantic_scholar": [
                paper("semantic_scholar", "Shared Research Title", doi="10/a")
            ],
            "open_alex": [paper("open_alex", "Shared Research Title", doi="10/b")],
        }
    )
    assert len(merged) == 2


def test_title_only_bridge_cannot_join_conflicting_identifier_clusters():
    merged = dedup(
        {
            "semantic_scholar": [
                paper("semantic_scholar", "Shared Research Title", doi="10/a")
            ],
            "open_alex": [paper("open_alex", "Shared Research Title", doi="10/b")],
            "arxiv": [paper("arxiv", "Shared Research Title")],
        }
    )
    assert len(merged) == 2
    assert sorted(len(item["found_in"]) for item in merged) == [1, 2]


def test_compatible_title_fallback_records_reason_and_confidence():
    merged = dedup(
        {
            "open_alex": [paper("open_alex", "Reliable Widget Gating")],
            "arxiv": [paper("arxiv", "Reliable Widget Gating")],
        }
    )
    assert len(merged) == 1
    assert merged[0]["dedup_match_reasons"] == ["title_metadata"]
    assert merged[0]["dedup_confidence"] == "title_metadata"


def test_generic_cross_source_title_is_not_a_key():
    merged = dedup(
        {
            "open_alex": [paper("open_alex", "Editorial")],
            "crossref": [paper("crossref", "Editorial")],
        }
    )
    assert len(merged) == 2


def test_rank_uses_query_coverage_and_native_rank_before_citations():
    broad = paper(
        "arxiv",
        "Broad retrieval result",
        citation_count=100,
        retrieval_ranks=[{"query": "broad", "rank": 1, "source": "arxiv"}],
    )
    covered = paper(
        "open_alex",
        "Broad exact target",
        retrieval_ranks=[
            {"query": "broad", "rank": 4, "source": "open_alex"},
            {"query": "exact target", "rank": 2, "source": "open_alex"},
        ],
    )
    ranked, _ = rank([broad, covered], ["broad", "exact target"])
    assert ranked[0]["title"] == "Broad exact target"
    assert ranked[0]["query_coverage"] == 2


def test_dedup_keeps_date_and_precision_from_same_best_record():
    merged = dedup(
        {
            "semantic_scholar": [
                paper(
                    "semantic_scholar",
                    "Reliable Widget Gating",
                    publication_date="2025",
                    date_precision="year",
                )
            ],
            "open_alex": [
                paper(
                    "open_alex",
                    "Reliable Widget Gating",
                    publication_date="2025-03-04",
                    date_precision="day",
                )
            ],
        }
    )
    assert merged[0]["publication_date"] == "2025-03-04"
    assert merged[0]["date_precision"] == "day"
    assert merged[0]["field_provenance"]["date_precision"] == "open_alex"


def test_arxiv_id_crosswalk_merges_changed_titles():
    merged = dedup(
        {
            "arxiv": [
                paper(
                    "arxiv",
                    "Scaling over Scaling: Plateau",
                    arxiv_id="2505.20522",
                )
            ],
            "dblp": [
                paper(
                    "dblp",
                    "Scaling over Scaling: Pareto",
                    doi="10.48550/arXiv.2505.20522",
                    arxiv_id="2505.20522",
                )
            ],
        }
    )
    assert len(merged) == 1
    assert "arxiv_id" in merged[0]["dedup_match_reasons"]
