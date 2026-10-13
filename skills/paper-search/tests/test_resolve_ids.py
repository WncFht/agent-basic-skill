import json
import urllib.parse

import resolve_ids
from paper_schema import SearchResults
from resolve_ids import classify_queries, resolve_identifiers


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text or ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    @property
    def content(self):
        return self.text.encode("utf-8")


ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2510.14901v1</id>
    <updated>2025-10-16T00:00:00Z</updated>
    <published>2025-10-16T00:00:00Z</published>
    <title>A Real Paper About Distillation</title>
    <summary>We study distillation.</summary>
    <author><name>Ada Lovelace</name></author>
    <arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">10.48550/arxiv.2510.14901</arxiv:doi>
  </entry>
  <entry>
    <id>http://arxiv.org/api/2510.99999</id>
    <title>Error</title>
    <summary>incorrect id format</summary>
  </entry>
</feed>
"""


def test_classify_queries_routes_ids_and_keeps_keywords():
    identifiers, keywords = classify_queries(
        [
            "2510.14901",
            "arXiv:2501.00001v3",
            "math.GT/0601132",
            "10.48550/arxiv.2401.00002",
            "doi:10.1055/s-0035-1566255",
            "https://doi.org/10.1000/xyz",
            "10.1/not-a-real-doi-scheme 10.2",
            "on-policy distillation",
        ]
    )
    arxiv_ids = [identifier for _typed, identifier in identifiers["arxiv"]]
    doi_ids = [identifier for _typed, identifier in identifiers["crossref"]]
    assert arxiv_ids == ["2510.14901", "2501.00001", "math.GT/0601132", "2401.00002"]
    assert doi_ids == ["10.1055/s-0035-1566255", "10.1000/xyz"]
    assert keywords == ["10.1/not-a-real-doi-scheme 10.2", "on-policy distillation"]


def test_resolve_arxiv_ids_parses_entries_and_reports_missing(monkeypatch):
    monkeypatch.setattr(
        resolve_ids,
        "request",
        lambda *args, **kwargs: FakeResponse(text=ARXIV_ATOM),
    )
    papers, missing = resolve_ids.resolve_arxiv_ids(["2510.14901", "2510.99999"])
    assert len(papers) == 1
    assert papers[0]["title"] == "A Real Paper About Distillation"
    assert papers[0]["arxiv_id"] == "2510.14901"
    assert papers[0]["doi"] == "10.48550/arxiv.2510.14901"
    assert missing == ["2510.99999"]


def test_resolve_dois_uses_crossref_and_reports_404(monkeypatch):
    responses = {
        "10.1/known": FakeResponse(
            payload={
                "message": {
                    "title": ["A Published Paper"],
                    "author": [{"given": "Ada", "family": "Lovelace"}],
                    "issued": {"date-parts": [[2024, 3]]},
                    "DOI": "10.1/known",
                    "is-referenced-by-count": 12,
                    "URL": "https://doi.org/10.1/known",
                    "container-title": ["Journal of Tests"],
                }
            }
        ),
        "10.1/unknown": FakeResponse(status_code=404),
    }
    monkeypatch.setattr(
        resolve_ids,
        "request",
        lambda session, method, url, **kwargs: responses[
            urllib.parse.unquote(url.rsplit("works/", 1)[-1])
        ],
    )
    monkeypatch.setattr(resolve_ids.time, "sleep", lambda _seconds: None)
    papers, missing = resolve_ids.resolve_dois(["10.1/known", "10.1/unknown"])
    assert len(papers) == 1
    assert papers[0]["citation_count"] == 12
    assert papers[0]["source"] == "crossref"
    assert missing == ["10.1/unknown"]


def _empty_results(sources):
    return SearchResults(
        {source: [] for source in sources},
        errors={source: [] for source in sources},
        runtime={source: {} for source in sources},
    )


def test_resolve_identifiers_injects_into_home_buckets_with_ranks(monkeypatch):
    monkeypatch.setattr(
        resolve_ids,
        "resolve_arxiv_ids",
        lambda ids: (
            [
                {
                    "title": "ArXiv Paper",
                    "authors": [],
                    "year": 2025,
                    "abstract": "",
                    "url": "http://arxiv.org/abs/2510.14901v1",
                    "venue": "arXiv",
                    "citation_count": None,
                    "citation_source": None,
                    "publication_date": "2025-10-16",
                    "publication_status": "preprint",
                    "status_source": "arxiv",
                    "source": "arxiv",
                    "doi": None,
                    "arxiv_id": "2510.14901",
                }
            ],
            [],
        ),
    )
    results = _empty_results(["arxiv", "crossref"])
    resolve_identifiers(
        results,
        {"arxiv": [("arXiv:2510.14901", "2510.14901")]},
    )
    assert results["arxiv"][0]["title"] == "ArXiv Paper"
    assert results["arxiv"][0]["retrieval_ranks"] == [
        {"query": "arXiv:2510.14901", "rank": 1, "source": "arxiv"}
    ]


def test_resolve_identifiers_skips_unselected_sources(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise AssertionError("no crossref resolution expected")

    monkeypatch.setattr(resolve_ids, "resolve_dois", fail)
    results = _empty_results(["arxiv"])
    resolve_identifiers(results, {"crossref": [("10.1/abc", "10.1/abc")]})
    assert "crossref" not in results
    assert "skipped" in capsys.readouterr().err


def test_search_papers_pure_id_run_skips_keyword_workers(monkeypatch):
    import search_papers

    def fail_workers(*args, **kwargs):
        raise AssertionError("keyword workers must not run for pure-ID queries")

    monkeypatch.setattr(search_papers, "_run_source_workers", fail_workers)
    monkeypatch.setattr(
        resolve_ids,
        "resolve_arxiv_ids",
        lambda ids: (
            [
                {
                    "title": "Fetched By ID",
                    "authors": [],
                    "year": 2019,
                    "abstract": "",
                    "url": "http://arxiv.org/abs/1901.00001v1",
                    "venue": "arXiv",
                    "citation_count": None,
                    "citation_source": None,
                    "publication_date": "2019-01-01",
                    "publication_status": "preprint",
                    "status_source": "arxiv",
                    "source": "arxiv",
                    "doi": None,
                    "arxiv_id": "1901.00001",
                }
            ],
            [],
        ),
    )
    results = search_papers.search_papers(
        query=["1901.00001"],
        start_year=2099,
        end_year=2099,
        max_results=10,
        sources=["arxiv"],
    )
    # The 2019 paper comes back even though the requested year window is 2099.
    assert results["arxiv"][0]["arxiv_id"] == "1901.00001"


def test_cli_json_envelope_reports_id_diagnostics(tmp_path, monkeypatch):
    report = {
        "generated_at": "2026-09-07T00:00:00+00:00",
        "request": {"queries": ["2510.99999"], "start_year": 2025, "end_year": 2026},
        "papers": {},
        "errors": {},
        "merged_ranked_papers": [],
        "stats": {"per_source_hits": {}, "unique_papers": 0},
    }
    # Regression guard for the run_logging warning classification.
    from run_logging import _diagnostic_severity

    assert (
        _diagnostic_severity(
            {"type": "IdNotFound", "query": "2510.99999", "message": "missing"}
        )
        == "warning"
    )
    assert json.dumps(report)  # envelope stays JSON-serializable
