"""Fill missing citation counts via batched OpenAlex DOI lookups.

Records from arXiv, OpenReview, and DBLP carry no citation metadata, so merged
reports show "N/A" for a large share of papers. Every OpenAlex work is
reachable by DOI, and arXiv preprints have DataCite DOIs
(``10.48550/arxiv.<id>``), so one batched ``filter=doi:a|b|c`` request per 50
records fills most gaps. Papers without any DOI or arXiv ID (OpenReview-only
records) cannot be looked up safely and are left untouched; title-based
matching is deliberately avoided because it invites false merges.
"""

from __future__ import annotations

import os
import time

from _http_runtime import create_session, polite_user_agent, request
from postprocess import norm_arxiv, norm_doi

_ARXIV_DOI_PREFIX = "10.48550/arxiv."
_CHUNK_SIZE = 50


def _enrichment_key(paper: dict) -> str | None:
    """Return the OpenAlex DOI key for one paper, or None when unidentifiable."""
    doi = norm_doi(paper.get("doi"))
    if doi:
        return doi
    arxiv_id = norm_arxiv(paper.get("arxiv_id"))
    if arxiv_id:
        return _ARXIV_DOI_PREFIX + arxiv_id
    return None


def enrich_citations(
    papers: list[dict],
    diagnostics: list[dict] | None = None,
    chunk_size: int = _CHUNK_SIZE,
) -> int:
    """Fill ``citation_count`` in place for papers that lack one.

    Returns the number of papers enriched. Lookup failures are appended to
    ``diagnostics`` (if given) and never raise; papers stay untouched so a
    report without enrichment remains valid.
    """
    candidates: dict[str, list[dict]] = {}
    for paper in papers:
        if paper.get("citation_count") is not None:
            continue
        key = _enrichment_key(paper)
        if key:
            candidates.setdefault(key, []).append(paper)
    if not candidates:
        return 0

    session = create_session(polite_user_agent())
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    keys = sorted(candidates)
    enriched = 0
    for start in range(0, len(keys), chunk_size):
        chunk = keys[start : start + chunk_size]
        params = {
            "filter": "doi:" + "|".join(chunk),
            "select": "doi,cited_by_count",
            "per-page": chunk_size,
        }
        try:
            response = request(
                session,
                "GET",
                "https://api.openalex.org/works",
                source="open_alex",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            items = response.json().get("results", [])
        except Exception as exc:
            if diagnostics is not None:
                diagnostics.append(
                    {
                        "query": None,
                        "type": "CitationEnrichmentError",
                        "message": f"OpenAlex citation lookup failed: {exc}",
                    }
                )
            continue
        for item in items:
            key = norm_doi(item.get("doi"))
            count = item.get("cited_by_count")
            if not key or count is None:
                continue
            for paper in candidates.get(key, []):
                paper["citation_count"] = int(count)
                paper["citation_source"] = "open_alex"
                enriched += 1
        if start + chunk_size < len(keys):
            time.sleep(1)  # Be polite to the API
    return enriched
