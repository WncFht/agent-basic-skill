#!/usr/bin/env python3
"""Offline contract tests for connector request shapes and normalized records."""

from __future__ import annotations

import os
import unittest
from unittest import mock

import paper_schema
import search_papers_by_arxiv
import search_papers_by_crossref
import search_papers_by_dblp
import search_papers_by_open_alex
import search_papers_by_semantic_scholar


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class SchemaTests(unittest.TestCase):
    def test_normalize_paper_produces_exact_public_fields(self):
        paper = paper_schema.normalize_paper(
            {"title": " Paper ", "authors": "Ada", "year": "2025"}, "arxiv"
        )
        self.assertEqual(tuple(paper), paper_schema.PAPER_FIELDS)
        self.assertEqual(paper["authors"], ["Ada"])
        self.assertEqual(paper["year"], 2025)
        self.assertEqual(paper["source"], "arxiv")
        self.assertIsNone(paper["citation_count"])
        self.assertEqual(paper["publication_status"], "unknown")

    def test_normalize_paper_rejects_empty_title_and_wrong_source(self):
        with self.assertRaisesRegex(ValueError, "title"):
            paper_schema.normalize_paper({}, "arxiv")
        with self.assertRaisesRegex(ValueError, "returned record"):
            paper_schema.normalize_paper({"title": "x", "source": "crossref"}, "arxiv")
        with self.assertRaisesRegex(ValueError, "citation_count"):
            paper_schema.normalize_paper({"title": "x", "citation_count": -1}, "arxiv")
        with self.assertRaisesRegex(ValueError, "publication_status"):
            paper_schema.normalize_paper(
                {"title": "x", "publication_status": "maybe"}, "arxiv"
            )


class OpenAlexTests(unittest.TestCase):
    @staticmethod
    def work(title="Paper"):
        return {
            "id": "https://openalex.org/W1",
            "title": title,
            "publication_year": 2025,
            "abstract_inverted_index": {"Hello": [0], "world": [1]},
            "doi": "https://doi.org/10.1/test",
            "authorships": [{"author": {"display_name": "Ada"}}],
            "primary_location": {"source": {"display_name": "Venue"}},
            "cited_by_count": 7,
            "publication_date": "2025-01-02",
            "type": "article",
        }

    def test_lexical_is_default_and_uses_select_and_cursor(self):
        response = Response(
            {"results": [self.work()], "meta": {"next_cursor": None, "count": 1}}
        )
        with mock.patch.object(
            search_papers_by_open_alex, "request", return_value=response
        ) as request:
            papers = search_papers_by_open_alex.search_papers_by_open_alex(
                "transformer", 2025, 2025, 1
            )
        params = request.call_args.kwargs["params"]
        self.assertEqual(params["search"], "transformer")
        self.assertNotIn("search.semantic", params)
        self.assertEqual(params["cursor"], "*")
        self.assertIn("abstract_inverted_index", params["select"])
        self.assertEqual(papers[0]["abstract"], "Hello world")
        self.assertEqual(papers[0]["publication_status"], "published")

    def test_semantic_mode_is_capped_and_not_paginated(self):
        diagnostics = []
        response = Response(
            {"results": [self.work()], "meta": {"next_cursor": "ignored", "count": 90}}
        )
        with mock.patch.object(
            search_papers_by_open_alex, "request", return_value=response
        ) as request:
            search_papers_by_open_alex.search_papers_by_open_alex(
                "transformer",
                2025,
                2025,
                80,
                diagnostics=diagnostics,
                source_options={"search_mode": "semantic"},
            )
        params = request.call_args.kwargs["params"]
        self.assertEqual(params["per-page"], 50)
        self.assertNotIn("cursor", params)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(diagnostics[0]["type"], "ResultLimitAdjusted")


class ConnectorHygieneTests(unittest.TestCase):
    def test_semantic_scholar_anonymous_429_has_actionable_diagnostic(self):
        response = Response({}, status_code=429)
        with (
            mock.patch.object(
                search_papers_by_semantic_scholar,
                "request",
                return_value=response,
            ),
            mock.patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("SEMANTICSCHOLAR_API_KEY", None)
            with self.assertRaisesRegex(RuntimeError, "anonymous access"):
                search_papers_by_semantic_scholar.search_papers_by_semantic_scholar(
                    "query", 2025, 2026, 1
                )

    def test_crossref_skips_empty_titles_and_cleans_jats(self):
        response = Response(
            {
                "message": {
                    "items": [
                        {"title": []},
                        {
                            "title": ["Paper"],
                            "abstract": "<jats:p>Hello &amp; world</jats:p>",
                            "published-online": {"date-parts": [[2025, 2, 3]]},
                        },
                    ],
                    "total-results": 2,
                }
            }
        )
        with mock.patch.object(
            search_papers_by_crossref, "request", return_value=response
        ):
            papers = search_papers_by_crossref.search_papers_by_crossref(
                "query", 2025, 2025, 2
            )
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["abstract"], "Hello & world")

    def test_dblp_abstract_enrichment_is_opt_in(self):
        response = Response(
            {
                "result": {
                    "hits": {
                        "@total": "1",
                        "hit": [
                            {
                                "info": {
                                    "title": "Paper",
                                    "year": "2025",
                                    "doi": "10.1/test",
                                }
                            }
                        ],
                    }
                }
            }
        )
        with (
            mock.patch.object(search_papers_by_dblp, "request", return_value=response),
            mock.patch.object(
                search_papers_by_dblp, "_fetch_abstract_from_doi"
            ) as enrich,
        ):
            search_papers_by_dblp.search_papers_by_dblp("query", 2025, 2025, 1)
        enrich.assert_not_called()

    def test_arxiv_expression_treats_query_as_data(self):
        expression = search_papers_by_arxiv._query_expression('cat:cs.AI OR "escape"')
        self.assertEqual(
            expression,
            'all:"cat" AND all:"cs" AND (all:"AI" OR all:"OR" OR all:"escape")',
        )
        self.assertNotIn("cat:", expression)
        strict = search_papers_by_arxiv._query_expression(
            'cat:cs.AI OR "escape"', mode="strict"
        )
        self.assertEqual(
            strict,
            'all:"cat" AND all:"cs" AND all:"AI" AND all:"OR" AND all:"escape"',
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
