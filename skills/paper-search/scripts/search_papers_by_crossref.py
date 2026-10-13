#!/usr/bin/env python3
"""Search for academic papers using the Crossref API."""

import argparse
import html
import re
import time

from _http_runtime import create_session, polite_user_agent, request


def crossref_item_to_paper(item: dict) -> dict | None:
    """Map one Crossref work item to the public schema; None when untitled."""
    authors = []
    for author in item.get("author", []):
        name_parts = []
        if author.get("given"):
            name_parts.append(author["given"])
        if author.get("family"):
            name_parts.append(author["family"])
        authors.append(" ".join(name_parts))

    date_parts = item.get("published-print", item.get("published-online", {})).get(
        "date-parts", [[None]]
    )[0]
    year = date_parts[0] if date_parts else None
    publication_date = None
    if date_parts and date_parts[0]:
        publication_date = "-".join(str(d).zfill(2) for d in date_parts if d)

    titles = item.get("title") or []
    title = str(titles[0]).strip() if titles else ""
    if not title:
        return None
    abstract = item.get("abstract", "") or ""
    abstract = html.unescape(re.sub(r"<[^>]+>", "", abstract)).strip()
    citation_count = item.get("is-referenced-by-count")
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "abstract": abstract,
        "url": item.get("URL", ""),
        "venue": " ".join(item.get("container-title", [])),
        "citation_count": citation_count,
        "citation_source": "crossref" if citation_count is not None else None,
        "publication_date": publication_date,
        "publication_status": "published",
        "status_source": "crossref",
        "source": "crossref",
        "doi": item.get("DOI"),
        "arxiv_id": None,
    }


def search_papers_by_crossref(
    query: str,
    start_year: int,
    end_year: int,
    max_results: int = 10,
) -> list[dict]:
    """Search for papers on Crossref.

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
    url = "https://api.crossref.org/works"
    papers: list[dict] = []
    offset = 0
    limit = min(100, max_results)  # API max per request is 100
    session = create_session(polite_user_agent())

    while len(papers) < max_results:
        params = {
            "query": query,
            "offset": offset,
            "rows": limit,
            "filter": f"from-pub-date:{start_year},until-pub-date:{end_year}",
            "sort": "relevance",
            "order": "desc",
        }
        response = request(session, "GET", url, source="crossref", params=params)
        response.raise_for_status()
        data = response.json()

        items = data.get("message", {}).get("items", [])
        if not items:
            break

        for item in items:
            paper = crossref_item_to_paper(item)
            if paper is not None:
                papers.append(paper)

        offset += limit
        total_results = data.get("message", {}).get("total-results", 0)

        if offset >= total_results:
            break

        time.sleep(1)  # Be polite to the API

    return papers[:max_results]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search papers on Crossref")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--start-year", type=int, required=True, help="Start year")
    parser.add_argument("--end-year", type=int, required=True, help="End year")
    parser.add_argument(
        "--max-papers", type=int, default=10, help="Max number of papers (default: 10)"
    )
    args = parser.parse_args()

    papers = search_papers_by_crossref(
        args.query, args.start_year, args.end_year, args.max_papers
    )
    print(papers[0] if papers else "No papers found.")

# python search_papers_by_crossref.py --query "data efficiency for model training" --start-year 2024 --end-year 2026 --max-papers 20
