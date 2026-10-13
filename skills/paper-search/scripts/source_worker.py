#!/usr/bin/env python3
"""Run exactly one paper-search connector and atomically persist its result."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from _env import load_env_once

load_env_once()

from _http_runtime import validate_environment
from paper_schema import PAPER_FIELDS, diagnostic, normalize_paper
from postprocess import dedup, rank_source_candidates
from source_registry import (
    API_SOURCES,
    SOURCE_SPECS,
    load_batch_connector,
    load_connector,
)

ALL_SOURCES = list(API_SOURCES)
_load_source_func = load_connector
_load_batch_source_func = load_batch_connector


def _error(query, exc: Exception) -> dict:
    return diagnostic(query, type(exc).__name__, str(exc))


def run_source(
    source: str,
    queries: list[str],
    start_year: int,
    end_year: int,
    max_results: int,
    source_options: dict | None = None,
) -> dict:
    """Collect per-query candidates, then deduplicate and cap the source result."""
    papers: list[dict] = []
    errors: list[dict] = []
    try:
        # Imports are connector execution too: keep any dependency warnings or
        # incidental prints out of stdout just like the search call itself.
        with contextlib.redirect_stdout(sys.stderr):
            func = _load_source_func(source)
    except Exception as exc:
        print(
            f"[{source}] unavailable (import failed: {exc}); skipping this source.",
            file=sys.stderr,
        )
        errors.append(_error(None, exc))
        return {"source": source, "papers": papers, "errors": errors}

    spec = SOURCE_SPECS[source]
    batch_func = None
    if len(queries) > 1 and spec.batch_function:
        try:
            with contextlib.redirect_stdout(sys.stderr):
                batch_func = _load_batch_source_func(source)
        except Exception as exc:
            print(
                f"[{source}] multi-query connector unavailable: {exc}; "
                "falling back to per-query calls.",
                file=sys.stderr,
            )

    if batch_func is not None:
        try:
            with contextlib.redirect_stdout(sys.stderr):
                kwargs = {"diagnostics": errors, "source_options": source_options or {}}
                raw_papers = batch_func(
                    queries, start_year, end_year, max_results, **kwargs
                )
            for raw_paper in raw_papers:
                try:
                    retrieval_ranks = list(raw_paper.get("retrieval_ranks") or [])
                    normalized = normalize_paper(raw_paper, source)
                    normalized["retrieval_ranks"] = retrieval_ranks
                    papers.append(normalized)
                except (TypeError, ValueError) as exc:
                    print(
                        f"[{source}] Invalid paper from multi-query search: {exc}",
                        file=sys.stderr,
                    )
                    errors.append(diagnostic(None, "InvalidPaper", str(exc)))
        except Exception as exc:
            print(f"[{source}] Multi-query search failed: {exc}", file=sys.stderr)
            errors.append(_error(None, exc))
    else:
        for query in queries:
            try:
                # A connector must never share stdout with the machine-readable result.
                with contextlib.redirect_stdout(sys.stderr):
                    kwargs = {}
                    if spec.accepts_diagnostics:
                        kwargs["diagnostics"] = errors
                    if spec.accepts_source_options:
                        kwargs["source_options"] = source_options or {}
                    raw_papers = func(
                        query, start_year, end_year, max_results, **kwargs
                    )
                    for query_rank, raw_paper in enumerate(raw_papers, 1):
                        try:
                            normalized = normalize_paper(raw_paper, source)
                            normalized["retrieval_ranks"] = [
                                {"query": query, "rank": query_rank, "source": source}
                            ]
                            papers.append(normalized)
                        except (TypeError, ValueError) as exc:
                            print(
                                f"[{source}] Invalid paper on query {query!r}: {exc}",
                                file=sys.stderr,
                            )
                            errors.append(diagnostic(query, "InvalidPaper", str(exc)))
            except Exception as exc:
                print(f"[{source}] Error on query {query!r}: {exc}", file=sys.stderr)
                errors.append(_error(query, exc))
                if getattr(exc, "abort_source", False):
                    print(
                        f"[{source}] remaining queries skipped for this run.",
                        file=sys.stderr,
                    )
                    break

    # Each query gets its own candidate budget, but the public contract is a
    # final per-source limit. Merge repeated records before applying that limit.
    merged = dedup({source: papers})
    merged = rank_source_candidates(merged, queries)[:max_results]
    papers = [
        {
            **{field: paper.get(field) for field in PAPER_FIELDS},
            "retrieval_ranks": list(paper.get("retrieval_ranks") or []),
        }
        for paper in merged
    ]
    return {"source": source, "papers": papers, "errors": errors}


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=ALL_SOURCES)
    parser.add_argument("--queries-json", required=True)
    parser.add_argument("--start-year", required=True, type=int)
    parser.add_argument("--end-year", required=True, type=int)
    parser.add_argument("--max-results", default=10, type=int)
    parser.add_argument("--source-options-json", default="{}")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    queries = json.loads(args.queries_json)
    if (
        not isinstance(queries, list)
        or not queries
        or not all(isinstance(query, str) and query for query in queries)
    ):
        parser.error("--queries-json must be a non-empty JSON array of strings")
    if args.max_results < 0:
        parser.error("--max-results must be >= 0")
    try:
        source_options = json.loads(args.source_options_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--source-options-json must be valid JSON: {exc}")
    if not isinstance(source_options, dict):
        parser.error("--source-options-json must be a JSON object")

    validate_environment([args.source])
    started = time.monotonic()
    payload = run_source(
        args.source,
        queries,
        args.start_year,
        args.end_year,
        args.max_results,
        source_options,
    )
    payload["duration_seconds"] = round(time.monotonic() - started, 3)
    write_atomic(args.out, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
