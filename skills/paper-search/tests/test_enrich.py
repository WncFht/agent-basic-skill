import enrich


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _paper(doi=None, arxiv_id=None, citations=None, source="arxiv"):
    return {
        "title": "Some Paper",
        "authors": ["Ada Lovelace"],
        "year": 2025,
        "abstract": "",
        "url": "",
        "venue": "",
        "citation_count": citations,
        "citation_source": None,
        "publication_date": "2025-01-01",
        "date_precision": "day",
        "publication_status": "preprint",
        "status_source": None,
        "source": source,
        "doi": doi,
        "arxiv_id": arxiv_id,
    }


def test_enriches_missing_citations_by_doi_and_arxiv(monkeypatch):
    filters = []

    def fake_request(session, method, url, *, source, params=None, **kwargs):
        filters.append(params["filter"])
        return FakeResponse(
            {
                "results": [
                    {"doi": "https://doi.org/10.1/foo", "cited_by_count": 7},
                    {
                        "doi": "https://doi.org/10.48550/arxiv.2501.00001",
                        "cited_by_count": 3,
                    },
                ]
            }
        )

    monkeypatch.setattr(enrich, "request", fake_request)
    monkeypatch.setattr(enrich.time, "sleep", lambda _seconds: None)
    papers = [_paper(doi="10.1/foo"), _paper(arxiv_id="2501.00001v2")]

    assert enrich.enrich_citations(papers) == 2
    assert papers[0]["citation_count"] == 7
    assert papers[0]["citation_source"] == "open_alex"
    assert papers[1]["citation_count"] == 3
    assert filters == ["doi:10.1/foo|10.48550/arxiv.2501.00001"]


def test_skips_papers_with_counts_or_without_ids(monkeypatch):
    def fail_request(*args, **kwargs):
        raise AssertionError("no lookup expected")

    monkeypatch.setattr(enrich, "request", fail_request)
    papers = [
        _paper(doi="10.1/has-count", citations=5),
        _paper(source="openreview"),
    ]
    assert enrich.enrich_citations(papers) == 0
    assert papers[0]["citation_source"] is None


def test_chunks_lookups_beyond_batch_size(monkeypatch):
    filters = []
    sleeps = []

    def fake_request(session, method, url, *, source, params=None, **kwargs):
        filters.append(params["filter"])
        return FakeResponse({"results": []})

    monkeypatch.setattr(enrich, "request", fake_request)
    monkeypatch.setattr(enrich.time, "sleep", sleeps.append)
    papers = [_paper(doi=f"10.1000/paper-{index}") for index in range(51)]

    assert enrich.enrich_citations(papers) == 0
    assert len(filters) == 2
    assert sleeps == [1]


def test_lookup_failure_appends_diagnostic_and_keeps_papers(monkeypatch):
    def fake_request(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr(enrich, "request", fake_request)
    diagnostics = []
    paper = _paper(doi="10.1/foo")

    assert enrich.enrich_citations([paper], diagnostics) == 0
    assert paper["citation_count"] is None
    assert [item["type"] for item in diagnostics] == ["CitationEnrichmentError"]
