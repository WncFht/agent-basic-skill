"""Stable paper-search records and JSON-safe result envelopes."""

from __future__ import annotations

import re
from collections.abc import Mapping

PAPER_FIELDS = (
    "title",
    "authors",
    "year",
    "abstract",
    "url",
    "venue",
    "citation_count",
    "citation_source",
    "publication_date",
    "date_precision",
    "publication_status",
    "status_source",
    "source",
    "doi",
    "arxiv_id",
)

PUBLICATION_STATUSES = frozenset(
    {
        "accepted",
        "published",
        "preprint",
        "submitted",
        "withdrawn",
        "rejected",
        "unknown",
    }
)

_ARXIV_ID_RE = re.compile(
    r"(?i)(?:10\.48550/arxiv\.|arxiv\.org/(?:abs|pdf)/|arxiv:)([a-z-]+(?:\.[a-z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?"
)


def infer_date_precision(value) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return "day"
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return "month"
    if re.fullmatch(r"\d{4}", text):
        return "year"
    return "unknown"


def infer_arxiv_id(paper: Mapping) -> str | None:
    explicit = str(paper.get("arxiv_id") or "").strip()
    if explicit:
        match = _ARXIV_ID_RE.search(f"arXiv:{explicit}")
        return match.group(1) if match else explicit
    for value in (paper.get("doi"), paper.get("url")):
        match = _ARXIV_ID_RE.search(str(value or ""))
        if match:
            return match.group(1)
    return None


def normalize_paper(paper: Mapping, source: str) -> dict:
    """Normalize one connector record to the public schema."""
    if not isinstance(paper, Mapping):
        raise TypeError(f"paper must be a mapping, got {type(paper).__name__}")

    authors = paper.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    elif not isinstance(authors, (list, tuple)):
        authors = list(authors)

    year = paper.get("year")
    if year not in (None, ""):
        try:
            year = int(year)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid paper year {year!r}") from exc
        if year <= 0:
            raise ValueError(f"invalid paper year {year!r}")

    citations = paper.get("citation_count")
    if citations not in (None, ""):
        try:
            citations = int(citations)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid citation_count {citations!r}") from exc
    else:
        citations = None
    if citations is not None and citations < 0:
        raise ValueError(f"invalid citation_count {citations!r}")

    publication_status = (
        str(paper.get("publication_status") or "unknown").strip().lower()
    )
    if publication_status not in PUBLICATION_STATUSES:
        raise ValueError(f"invalid publication_status {publication_status!r}")
    citation_source = (
        str(paper.get("citation_source") or source).strip()
        if citations is not None
        else None
    )
    status_source = (
        str(paper.get("status_source") or source).strip()
        if publication_status != "unknown"
        else None
    )

    publication_date = str(paper.get("publication_date") or "").strip()
    date_precision = (
        str(paper.get("date_precision") or infer_date_precision(publication_date))
        .strip()
        .lower()
    )
    if date_precision not in {"day", "month", "year", "unknown"}:
        raise ValueError(f"invalid date_precision {date_precision!r}")

    normalized = {
        "title": str(paper.get("title") or "").strip(),
        "authors": [str(author).strip() for author in authors if str(author).strip()],
        "year": year,
        "abstract": str(paper.get("abstract") or "").strip(),
        "url": str(paper.get("url") or "").strip(),
        "venue": str(paper.get("venue") or "").strip(),
        "citation_count": citations,
        "citation_source": citation_source,
        "publication_date": publication_date,
        "date_precision": date_precision,
        "publication_status": publication_status,
        "status_source": status_source,
        "source": str(paper.get("source") or source).strip(),
        "doi": paper.get("doi") or None,
        "arxiv_id": infer_arxiv_id(paper),
    }
    if normalized["source"] != source:
        raise ValueError(
            f"connector {source!r} returned record for {normalized['source']!r}"
        )
    if not normalized["title"]:
        raise ValueError("paper title must not be empty")
    return normalized


def diagnostic(query, error_type: str, message: str) -> dict:
    return {"query": query, "type": str(error_type), "message": str(message)}


class SearchResults(dict):
    """Backward-compatible source mapping with structured diagnostics."""

    def __init__(self, papers_by_source=None, errors=None, runtime=None):
        super().__init__(papers_by_source or {})
        self.errors = {
            source: list((errors or {}).get(source, [])) for source in self.keys()
        }
        self.runtime = {
            source: dict((runtime or {}).get(source, {})) for source in self.keys()
        }

    def to_dict(self) -> dict:
        """Return an explicit JSON-serializable envelope without losing errors."""
        return {
            "papers": {source: list(papers) for source, papers in self.items()},
            "errors": {source: list(items) for source, items in self.errors.items()},
        }
