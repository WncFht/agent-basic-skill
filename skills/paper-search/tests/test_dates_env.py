import os

import _env
import pytest
from _http_runtime import get_source_budget
from paper_schema import infer_arxiv_id, infer_date_precision, normalize_paper
from search_papers import _filter_by_date_range, _parse_date
from source_registry import DEFAULT_MAX_RESULTS, DEFAULT_SOURCES


def test_defaults_prefer_stable_sources_and_give_openreview_more_time():
    assert DEFAULT_SOURCES == ("open_alex", "openreview", "crossref")
    assert DEFAULT_MAX_RESULTS == 50
    assert get_source_budget("openreview") == 600.0
    assert get_source_budget("open_alex") == 180.0


def test_date_precision_is_derived_for_normalized_records():
    assert infer_date_precision("2025-02-03") == "day"
    assert infer_date_precision("2025-02") == "month"
    assert infer_date_precision("2025") == "year"
    assert infer_date_precision("") == "unknown"
    normalized = normalize_paper(
        {"title": "Paper", "publication_date": "2025-02"}, "crossref"
    )
    assert normalized["date_precision"] == "month"


def test_arxiv_id_is_inferred_from_doi_or_url():
    assert infer_arxiv_id({"doi": "10.48550/arXiv.2505.20522"}) == "2505.20522"
    assert infer_arxiv_id({"url": "https://arxiv.org/abs/2401.12345v2"}) == "2401.12345"
    normalized = normalize_paper(
        {"title": "Paper", "doi": "10.48550/arXiv.2505.20522"}, "dblp"
    )
    assert normalized["arxiv_id"] == "2505.20522"


def test_coarse_date_filter_uses_interval_overlap():
    papers = [
        {"title": "year", "publication_date": "2025", "date_precision": "year"},
        {"title": "month", "publication_date": "2025-02", "date_precision": "month"},
        {"title": "day", "publication_date": "2025-03-01", "date_precision": "day"},
    ]
    filtered = _filter_by_date_range(
        papers, _parse_date("2025-02-15", "start"), _parse_date("2025-02-20", "end")
    )
    assert [paper["title"] for paper in filtered] == ["year", "month"]


def test_env_loader_rejects_invalid_keys_without_leaking_values(tmp_path):
    path = tmp_path / ".env"
    path.write_text("INVALID-KEY=secret\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="invalid environment key"):
        _env._apply(path)
    assert "INVALID-KEY" not in os.environ
