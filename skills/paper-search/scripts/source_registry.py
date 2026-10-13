"""Single source of truth for searchable API connectors and their options."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    module: str
    options: frozenset[str] = frozenset()
    accepts_diagnostics: bool = False
    accepts_source_options: bool = False
    batch_function: str | None = None


SOURCE_SPECS = {
    "semantic_scholar": SourceSpec("search_papers_by_semantic_scholar"),
    "open_alex": SourceSpec(
        "search_papers_by_open_alex",
        frozenset({"search_mode"}),
        accepts_diagnostics=True,
        accepts_source_options=True,
    ),
    "arxiv": SourceSpec(
        "search_papers_by_arxiv",
        frozenset({"query_mode"}),
        accepts_source_options=True,
    ),
    "openreview": SourceSpec(
        "search_papers_by_openreview",
        frozenset(
            {
                "venues",
                "mode",
                "api_version",
                "status",
                "scan_limit_per_venue",
            }
        ),
        accepts_diagnostics=True,
        accepts_source_options=True,
        batch_function="search_papers_by_openreview_queries",
    ),
    "crossref": SourceSpec("search_papers_by_crossref"),
    "dblp": SourceSpec(
        "search_papers_by_dblp",
        frozenset({"enrich_abstracts"}),
        accepts_diagnostics=True,
        accepts_source_options=True,
    ),
}

API_SOURCES = tuple(SOURCE_SPECS)
DEFAULT_SOURCES = ("open_alex", "openreview", "crossref")
DEFAULT_MAX_RESULTS = 50


def load_connector(source: str) -> Callable:
    """Load one registered connector without importing unrelated dependencies."""
    spec = SOURCE_SPECS[source]
    module = importlib.import_module(spec.module)
    return getattr(module, spec.module)


def load_batch_connector(source: str) -> Callable | None:
    """Load a connector's native multi-query entry point when available."""
    spec = SOURCE_SPECS[source]
    if spec.batch_function is None:
        return None
    module = importlib.import_module(spec.module)
    return getattr(module, spec.batch_function)
