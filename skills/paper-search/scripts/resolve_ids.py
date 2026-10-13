"""Direct resolution for ID-form queries (arXiv IDs and DOIs).

Queries that are already identifiers must not run through keyword search:
the arXiv full-text index does not contain bare IDs, so a query like
"2510.14901" reliably returns zero results. This module classifies such
queries and resolves them against the authoritative registry in one batch
per ID type: arXiv IDs (including ``10.48550/arxiv.*`` DOI forms) via the
arXiv ``id_list`` endpoint, other DOIs via Crossref.

Resolved records are injected into their home source bucket (arXiv IDs ->
``arxiv``, DOIs -> ``crossref``) and bypass year/date filtering: the intent
when pasting an ID is "fetch this paper", not "filter by year".
"""

from __future__ import annotations

import re
import sys
import time
import urllib.parse

from _http_runtime import create_session, polite_user_agent, request
from paper_schema import diagnostic, normalize_paper
from postprocess import norm_arxiv, norm_doi

# Old-style IDs ("math.GT/0601132") are case-sensitive; only the "arxiv:"
# prefix is matched case-insensitively. The 10.48550/arxiv.* DataCite form is
# an arXiv ID in disguise and resolves through the same endpoint.
_ARXIV_ID_RE = re.compile(
    r"^(?i:arxiv:)?(?P<id>[A-Za-z-]+(?:\.[A-Za-z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?$"
)
_ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(?P<id>\S+)$", re.IGNORECASE)
_DOI_RE = re.compile(
    r"^(?:doi:|https?://doi\.org/)?(?P<id>10\.\d{4,9}/\S+)$", re.IGNORECASE
)
_ARXIV_CHUNK = 100


def classify_queries(
    queries: list[str],
) -> tuple[dict[str, list[tuple[str, str]]], list[str]]:
    """Split queries into ``{home_source: [(typed_query, identifier), ...]}``.

    The typed query is kept verbatim for retrieval-rank provenance; the
    identifier is the normalized ID to resolve. Everything that is not an
    ID comes back unchanged as keyword queries.
    """
    identifiers: dict[str, list[tuple[str, str]]] = {}
    keywords: list[str] = []
    for query in queries:
        stripped = query.strip()
        arxiv_doi = _ARXIV_DOI_RE.match(stripped)
        arxiv_id = _ARXIV_ID_RE.match(stripped)
        doi = _DOI_RE.match(stripped)
        if arxiv_doi:
            identifiers.setdefault("arxiv", []).append(
                (stripped, arxiv_doi.group("id"))
            )
        elif arxiv_id:
            identifiers.setdefault("arxiv", []).append((stripped, arxiv_id.group("id")))
        elif doi:
            identifiers.setdefault("crossref", []).append((stripped, doi.group("id")))
        else:
            keywords.append(query)
    return identifiers, keywords


def _dedupe(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Map each unique identifier to the queries that reference it."""
    by_id: dict[str, list[str]] = {}
    for typed_query, identifier in pairs:
        by_id.setdefault(identifier, []).append(typed_query)
    return by_id


def resolve_arxiv_ids(
    ids: list[str],
) -> tuple[list[dict], list[str]]:
    """Fetch papers for arXiv IDs in one batched ``id_list`` request.

    Returns ``(papers, missing_ids)``. Entries the API answers with an error
    placeholder (malformed or unknown IDs) are skipped and reported as
    missing.
    """
    from search_papers_by_arxiv import _parse_arxiv_xml, _throttle

    papers: list[dict] = []
    session = create_session("PaperSearch/1.0")
    for start in range(0, len(ids), _ARXIV_CHUNK):
        chunk = ids[start : start + _ARXIV_CHUNK]
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"id_list": ",".join(chunk), "max_results": str(len(chunk))}
        )
        response = request(
            session, "GET", url, source="arxiv", before_attempt=_throttle
        )
        response.raise_for_status()
        papers.extend(_parse_arxiv_xml(response.content.decode("utf-8"), 1, 9999))
    returned = {paper.get("arxiv_id") for paper in papers}
    missing = [arxiv_id for arxiv_id in ids if arxiv_id not in returned]
    return papers, missing


def resolve_dois(dois: list[str]) -> tuple[list[dict], list[str]]:
    """Fetch papers for DOIs via Crossref, one request per DOI.

    Returns ``(papers, missing_dois)``. Crossref covers Crossref-registered
    DOIs only; DataCite-issued DOIs (other than the arXiv 10.48550 form,
    which classify_queries routes to arXiv) surface as missing.
    """
    from search_papers_by_crossref import crossref_item_to_paper

    session = create_session(polite_user_agent())
    papers: list[dict] = []
    missing: list[str] = []
    for index, doi in enumerate(dois):
        encoded = urllib.parse.quote(doi, safe="")
        response = request(
            session,
            "GET",
            f"https://api.crossref.org/works/{encoded}",
            source="crossref",
            headers={"Accept": "application/json"},
        )
        if response.status_code == 404:
            missing.append(doi)
            continue
        response.raise_for_status()
        paper = crossref_item_to_paper(response.json().get("message", {}))
        if paper is not None:
            papers.append(paper)
        else:
            missing.append(doi)
        if index + 1 < len(dois):
            time.sleep(1)  # Be polite to the API
    return papers, missing


def _queries_for_paper(paper: dict, by_id: dict[str, list[str]]) -> list[str]:
    """Match a resolved paper back to the typed queries via normalized IDs."""
    for value in (norm_arxiv(paper.get("arxiv_id")), norm_doi(paper.get("doi"))):
        if value and value in by_id:
            return by_id[value]
    return []


def resolve_identifiers(results, identifiers: dict[str, list[tuple[str, str]]]) -> None:
    """Inject ID-resolved records into their home source buckets, in place.

    Records outside the selected sources are skipped with a stderr note;
    resolution failures become warnings so a typo cannot fail the run.
    """
    for source, pairs in identifiers.items():
        by_id = _dedupe(pairs)
        if source not in results:
            print(
                f"[id-lookup] {len(by_id)} {source} identifier(s) skipped: "
                f"{source} is not in the selected sources.",
                file=sys.stderr,
            )
            continue
        try:
            if source == "arxiv":
                papers, missing = resolve_arxiv_ids(list(by_id))
            else:
                papers, missing = resolve_dois(list(by_id))
        except Exception as exc:
            print(f"[id-lookup] {source} resolution failed: {exc}", file=sys.stderr)
            results.errors[source].append(
                diagnostic(None, type(exc).__name__, f"ID resolution failed: {exc}")
            )
            continue
        injected = 0
        for raw_paper in papers:
            try:
                paper = normalize_paper(raw_paper, source)
            except (TypeError, ValueError) as exc:
                results.errors[source].append(
                    diagnostic(
                        None, "InvalidPaper", f"ID-resolved paper invalid: {exc}"
                    )
                )
                continue
            paper["retrieval_ranks"] = [
                {"query": typed, "rank": 1, "source": source}
                for typed in _queries_for_paper(paper, by_id)
            ]
            results[source].append(paper)
            injected += 1
        for identifier in missing:
            queries = by_id.get(identifier, [identifier])
            results.errors[source].append(
                diagnostic(
                    queries[0],
                    "IdNotFound",
                    f"identifier {identifier!r} was not found in {source}",
                )
            )
        print(
            f"[id-lookup] {source}: resolved {injected}/{len(by_id)} identifier(s)",
            file=sys.stderr,
            flush=True,
        )
