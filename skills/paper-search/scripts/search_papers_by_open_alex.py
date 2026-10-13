#!/usr/bin/env python3
"""Search for academic papers using the OpenAlex API."""

import argparse
import os
import time

from _http_runtime import create_session, request


def search_papers_by_open_alex(
    query: str,
    start_year: int,
    end_year: int,
    max_results: int = 10,
    diagnostics: list[dict] | None = None,
    source_options: dict | None = None,
) -> list[dict]:
    """Search for papers on OpenAlex.

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
    options = source_options or {}
    mode = str(options.get("search_mode", "lexical")).lower()
    if mode not in {"lexical", "semantic"}:
        raise ValueError("OpenAlex search_mode must be 'lexical' or 'semantic'")

    api_key = os.environ.get("OPENALEX_API_KEY", "")
    url = "https://api.openalex.org/works"
    papers: list[dict] = []
    semantic_limit = 50
    requested_limit = max_results
    if mode == "semantic" and max_results > semantic_limit:
        max_results = semantic_limit
        if diagnostics is not None:
            diagnostics.append(
                {
                    "query": query,
                    "type": "ResultLimitAdjusted",
                    "message": "OpenAlex semantic search is capped at 50 results",
                }
            )
    per_page = min(semantic_limit if mode == "semantic" else 200, max_results)
    cursor = "*"
    session = create_session("PaperSearch/1.0")

    while len(papers) < max_results:
        params = {
            "filter": f"publication_year:{start_year}-{end_year}",
            "per-page": per_page,
            "select": (
                "id,title,publication_year,abstract_inverted_index,doi,authorships,"
                "primary_location,cited_by_count,publication_date"
                ",type"
            ),
        }
        if mode == "semantic":
            params["search.semantic"] = query
        else:
            params["search"] = query
            params["cursor"] = cursor
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        response = request(
            session, "GET", url, source="open_alex", params=params, headers=headers
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            break

        for work in results:
            citation_count = work.get("cited_by_count")
            primary_location = work.get("primary_location") or {}
            work_type = str(work.get("type") or "").casefold()
            if work_type == "preprint":
                publication_status = "preprint"
            elif work_type in {
                "article",
                "book",
                "book-chapter",
                "dissertation",
                "proceedings-article",
            }:
                publication_status = "published"
            else:
                publication_status = "unknown"
            papers.append(
                {
                    "title": work.get("title", ""),
                    "authors": [
                        authorship["author"]["display_name"]
                        for authorship in work.get("authorships", [])
                        if authorship.get("author", {}).get("display_name")
                    ],
                    "year": work.get("publication_year"),
                    "abstract": _reconstruct_abstract(
                        work.get("abstract_inverted_index")
                    ),
                    "url": work.get("doi") or work.get("id", ""),
                    "venue": (primary_location.get("source") or {}).get(
                        "display_name", ""
                    ),
                    "citation_count": citation_count,
                    "citation_source": "open_alex"
                    if citation_count is not None
                    else None,
                    "publication_date": work.get("publication_date", ""),
                    "publication_status": publication_status,
                    "status_source": "open_alex",
                    "source": "open_alex",
                    "doi": (work.get("doi") or "").replace("https://doi.org/", "")
                    or None,
                    "arxiv_id": None,
                }
            )

        if mode == "semantic":
            break
        next_cursor = data.get("meta", {}).get("next_cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

        time.sleep(1)  # Be polite to the API

    return papers[: min(requested_limit, max_results)]


def _reconstruct_abstract(
    inverted_index,
) -> str:  # dict | None (3.9-safe: no runtime union)
    """Reconstruct abstract text from OpenAlex inverted index format."""
    if not inverted_index:
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(word for _, word in word_positions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search papers on OpenAlex")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--start-year", type=int, required=True, help="Start year")
    parser.add_argument("--end-year", type=int, required=True, help="End year")
    parser.add_argument(
        "--max-papers", type=int, default=10, help="Max number of papers (default: 10)"
    )
    parser.add_argument(
        "--search-mode", choices=("lexical", "semantic"), default="lexical"
    )
    args = parser.parse_args()

    papers = search_papers_by_open_alex(
        args.query,
        args.start_year,
        args.end_year,
        args.max_papers,
        source_options={"search_mode": args.search_mode},
    )
    print(papers[0] if papers else "No papers found.")

# python search_papers_by_open_alex.py --query "data efficacy for LM training" --start-year 2024 --end-year 2026 --max-papers 20
