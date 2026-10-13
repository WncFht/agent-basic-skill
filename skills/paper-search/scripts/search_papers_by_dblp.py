#!/usr/bin/env python3
"""Search for academic papers using the DBLP API."""

import argparse
import html
import re
import time
import urllib.parse

from _http_runtime import create_session, polite_user_agent, request


def search_papers_by_dblp(
    query: str,
    start_year: int,
    end_year: int,
    max_results: int = 10,
    diagnostics: list[dict] | None = None,
    source_options: dict | None = None,
) -> list[dict]:
    """Search for papers on DBLP.

    Args:
        query: Search query string.
        start_year: Filter papers published from this year.
        end_year: Filter papers published up to this year.
        max_results: Maximum number of papers to return.

    Returns:
        List of paper dictionaries.
    """
    if max_results <= 0:
        return []
    enrich_abstracts = bool((source_options or {}).get("enrich_abstracts", False))
    url = "https://dblp.org/search/publ/api"
    papers: list[dict] = []
    offset = 0
    limit = min(1000, max_results)  # DBLP max per request is 1000
    # DBLP asks clients to identify themselves with a contact address; generic
    # user agents see more 503s and dropped connections under load.
    session = create_session(polite_user_agent())

    while len(papers) < max_results:
        params = {
            "q": query,
            "format": "json",
            "h": limit,
            "f": offset,
        }

        response = request(
            session,
            "GET",
            url,
            source="dblp",
            params=params,
            backoff_base=5.0,
        )
        response.raise_for_status()
        data = response.json()

        hits = data.get("result", {}).get("hits", {})
        total = int(hits.get("@total", 0))
        hit_list = hits.get("hit", [])

        if not hit_list:
            break

        for hit in hit_list:
            info = hit.get("info", {})
            year = int(info.get("year", 0))

            # Filter by year range
            if year < start_year or year > end_year:
                continue

            # Normalize authors
            authors_info = info.get("authors", {}).get("author", [])
            if isinstance(authors_info, dict):
                authors_info = [authors_info]
            authors = [
                a.get("text", "") if isinstance(a, dict) else a for a in authors_info
            ]

            papers.append(
                {
                    "title": info.get("title", ""),
                    "authors": authors,
                    "year": year,
                    "abstract": "",
                    "url": info.get("ee", info.get("url", "")),
                    "venue": info.get("venue", ""),
                    "citation_count": None,
                    "citation_source": None,
                    "publication_date": f"{year}-01-01",
                    "date_precision": "year",
                    "publication_status": "published",
                    "status_source": "dblp",
                    "source": "dblp",
                    "doi": info.get("doi"),
                    "arxiv_id": None,
                }
            )

        offset += limit

        if offset >= total:
            break

        time.sleep(1)  # Be polite to the API

    papers = papers[:max_results]
    if enrich_abstracts:
        for paper in papers:
            doi = paper.get("doi")
            if not doi:
                continue
            try:
                abstract = _fetch_abstract_from_doi(doi, session=session)
                if abstract:
                    paper["abstract"] = abstract
            except Exception as exc:
                if diagnostics is not None:
                    diagnostics.append(
                        {
                            "query": query,
                            "type": type(exc).__name__,
                            "message": f"Crossref enrichment failed for {doi}: {exc}",
                        }
                    )
            time.sleep(0.5)

    return papers


def _fetch_abstract_from_doi(doi: str, session=None) -> str:
    """Fetch an abstract from Crossref for a normalized DOI."""
    if not doi:
        return ""
    session = session or create_session("PaperSearch/1.0")
    encoded_doi = urllib.parse.quote(doi, safe="")
    resp = request(
        session,
        "GET",
        f"https://api.crossref.org/works/{encoded_doi}",
        source="dblp",
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    abstract = resp.json().get("message", {}).get("abstract", "")
    return html.unescape(re.sub(r"<[^>]+>", "", abstract)).strip() if abstract else ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search papers on DBLP")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--start-year", type=int, required=True, help="Start year")
    parser.add_argument("--end-year", type=int, required=True, help="End year")
    parser.add_argument(
        "--max-papers", type=int, default=10, help="Max number of papers (default: 10)"
    )
    args = parser.parse_args()

    papers = search_papers_by_dblp(
        args.query, args.start_year, args.end_year, args.max_papers
    )
    print(papers[0] if papers else "No papers found.")

# python search_papers_by_dblp.py --query "data efficiency for model training" --start-year 2024 --end-year 2026 --max-papers 20
