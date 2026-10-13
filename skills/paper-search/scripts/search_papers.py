#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#     "requests",
#     "openreview-py",
# ]
# ///
"""Unified interface to search for academic papers across multiple sources.

Supported sources: arXiv, DBLP, OpenAlex, OpenReview, Semantic Scholar,
and Crossref.

Post-processing (default ON, see postprocess.py): cross-source dedup with a
`found_in` provenance column, lexical relevance ranking against the query,
survey tagging (sunk, never dropped), and an opt-in --min-score filter that
prints exactly what it dropped. --raw restores the legacy per-source view.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path

# Load repository-local credentials before workers inherit the environment.
from _env import load_env_once
from _http_runtime import get_source_budget, validate_environment
from paper_schema import SearchResults, diagnostic, infer_date_precision
from resolve_ids import classify_queries, resolve_identifiers
from source_registry import (
    API_SOURCES,
    DEFAULT_MAX_RESULTS,
    DEFAULT_SOURCES,
    SOURCE_SPECS,
)

load_env_once()

ALL_SOURCES = list(API_SOURCES)
_SCRIPTS_DIR = Path(__file__).resolve().parent
_SOURCE_WORKER = _SCRIPTS_DIR / "source_worker.py"


def _worker_error(error_type: str, message: str) -> dict:
    return diagnostic(None, error_type, message)


def _worker_command(
    source: str,
    queries: list[str],
    start_year: int,
    end_year: int,
    max_results: int,
    out_path: Path,
    source_options: dict | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(_SOURCE_WORKER),
        "--source",
        source,
        "--queries-json",
        json.dumps(queries, ensure_ascii=False),
        "--start-year",
        str(start_year),
        "--end-year",
        str(end_year),
        "--max-results",
        str(max_results),
        "--out",
        str(out_path),
    ]
    if source_options:
        command.extend(
            [
                "--source-options-json",
                json.dumps(source_options, ensure_ascii=False),
            ]
        )
    return command


def _start_worker(
    source: str,
    queries: list[str],
    start_year: int,
    end_year: int,
    max_results: int,
    work_dir: Path,
    source_options: dict | None = None,
) -> tuple[subprocess.Popen, Path, Path]:
    out_path = work_dir / f"{source}.json"
    log_path = work_dir / f"{source}.log"
    if source_options:
        command = _worker_command(
            source,
            queries,
            start_year,
            end_year,
            max_results,
            out_path,
            source_options=source_options,
        )
    else:
        command = _worker_command(
            source, queries, start_year, end_year, max_results, out_path
        )
    with log_path.open("w", encoding="utf-8") as log_handle:
        query_label = "query" if len(queries) == 1 else "queries"
        print(
            f"[{source}] started ({len(queries)} {query_label})",
            file=sys.stderr,
            flush=True,
        )
        process = subprocess.Popen(
            command,
            cwd=str(_SCRIPTS_DIR),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=(os.name == "posix"),
        )
        process._paper_search_started_at = time.monotonic()  # type: ignore[attr-defined]
    return process, out_path, log_path


def _terminate_workers(processes: list[subprocess.Popen]) -> None:
    alive = [process for process in processes if process.poll() is None]
    for process in alive:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            pass
    for process in alive:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
    for process in alive:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def _collect_worker(
    source: str,
    process: subprocess.Popen,
    out_path: Path,
    log_path: Path,
) -> tuple[list[dict], list[dict]]:
    started_at = getattr(process, "_paper_search_started_at", time.monotonic())
    budget = get_source_budget(source)
    remaining = max(0.0, budget - (time.monotonic() - started_at))
    try:
        returncode = process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        _terminate_workers([process])
        try:
            log = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log = ""
        if log:
            sys.stderr.write(log if log.endswith("\n") else log + "\n")
        message = f"source exceeded wall-clock budget of {budget:g}s"
        print(f"[{source}] {message}; skipping this source.", file=sys.stderr)
        return [], [_worker_error("SourceBudgetExceeded", message)]
    try:
        log = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log = f"[{source}] could not read worker log: {exc}\n"
    if log:
        sys.stderr.write(log)
        if not log.endswith("\n"):
            sys.stderr.write("\n")

    if returncode != 0:
        message = f"worker exited with status {returncode}; skipping this source."
        print(f"[{source}] {message}", file=sys.stderr)
        return [], [_worker_error("WorkerExitError", message)]
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"[{source}] worker produced no result file; skipping this source.",
            file=sys.stderr,
        )
        return [], [
            _worker_error("WorkerResultMissing", "worker produced no result file")
        ]
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"[{source}] invalid worker result: {exc}; skipping this source.",
            file=sys.stderr,
        )
        return [], [_worker_error("WorkerResultInvalid", str(exc))]

    if not isinstance(payload, dict) or payload.get("source") != source:
        print(
            f"[{source}] worker result has the wrong source; skipping it.",
            file=sys.stderr,
        )
        return [], [
            _worker_error("WorkerResultInvalid", "worker result has the wrong source")
        ]
    papers = payload.get("papers")
    if not isinstance(papers, list) or not all(
        isinstance(paper, dict) for paper in papers
    ):
        print(
            f"[{source}] worker result has invalid papers; skipping it.",
            file=sys.stderr,
        )
        return [], [
            _worker_error("WorkerResultInvalid", "worker result has invalid papers")
        ]
    errors = payload.get("errors", [])
    if not isinstance(errors, list) or not all(
        isinstance(error, dict) for error in errors
    ):
        print(
            f"[{source}] worker result has invalid errors; replacing diagnostics.",
            file=sys.stderr,
        )
        errors = [
            _worker_error("WorkerResultInvalid", "worker result has invalid errors")
        ]
    duration = payload.get("duration_seconds")
    if isinstance(duration, (int, float)) and duration >= 0:
        process._paper_search_duration_seconds = float(duration)  # type: ignore[attr-defined]
    print(
        f"[{source}] finished: {len(papers)} paper(s), {len(errors)} diagnostic(s)",
        file=sys.stderr,
        flush=True,
    )
    return papers, errors


def _run_source_workers(
    sources: list[str],
    queries: list[str],
    start_year: int,
    end_year: int,
    max_results: int,
    parallel: bool,
    source_options: dict[str, dict] | None = None,
) -> SearchResults:
    gathered: dict[str, list[dict]] = {}
    errors: dict[str, list[dict]] = {source: [] for source in sources}
    runtime: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="paper_search_workers_") as temp_dir:
        work_dir = Path(temp_dir)
        states: dict[str, tuple[subprocess.Popen, Path, Path]] = {}
        try:
            if parallel:
                for source in sources:
                    try:
                        options = (source_options or {}).get(source) or None
                        if options:
                            states[source] = _start_worker(
                                source,
                                queries,
                                start_year,
                                end_year,
                                max_results,
                                work_dir,
                                source_options=options,
                            )
                        else:
                            states[source] = _start_worker(
                                source,
                                queries,
                                start_year,
                                end_year,
                                max_results,
                                work_dir,
                            )
                    except OSError as exc:
                        print(
                            f"[{source}] worker could not start: {exc}", file=sys.stderr
                        )
                        gathered[source] = []
                        errors[source].append(
                            _worker_error(type(exc).__name__, str(exc))
                        )
                        runtime[source] = {
                            "duration_seconds": 0.0,
                            "worker_exit_code": None,
                        }
                # Every process is already running; collecting in requested order does
                # not serialize the network work and keeps diagnostics deterministic.
                for source in sources:
                    state = states.get(source)
                    if state is not None:
                        gathered[source], errors[source] = _collect_worker(
                            source, *state
                        )
                        started = getattr(state[0], "_paper_search_started_at", None)
                        duration = getattr(
                            state[0], "_paper_search_duration_seconds", None
                        )
                        runtime[source] = {
                            "duration_seconds": duration
                            if duration is not None
                            else (
                                round(time.monotonic() - started, 3)
                                if started is not None
                                else None
                            ),
                            "worker_exit_code": state[0].returncode,
                        }
            else:
                for source in sources:
                    try:
                        options = (source_options or {}).get(source) or None
                        if options:
                            state = _start_worker(
                                source,
                                queries,
                                start_year,
                                end_year,
                                max_results,
                                work_dir,
                                source_options=options,
                            )
                        else:
                            state = _start_worker(
                                source,
                                queries,
                                start_year,
                                end_year,
                                max_results,
                                work_dir,
                            )
                    except OSError as exc:
                        print(
                            f"[{source}] worker could not start: {exc}", file=sys.stderr
                        )
                        gathered[source] = []
                        errors[source].append(
                            _worker_error(type(exc).__name__, str(exc))
                        )
                        runtime[source] = {
                            "duration_seconds": 0.0,
                            "worker_exit_code": None,
                        }
                        continue
                    states[source] = state
                    gathered[source], errors[source] = _collect_worker(source, *state)
                    started = getattr(state[0], "_paper_search_started_at", None)
                    duration = getattr(state[0], "_paper_search_duration_seconds", None)
                    runtime[source] = {
                        "duration_seconds": duration
                        if duration is not None
                        else (
                            round(time.monotonic() - started, 3)
                            if started is not None
                            else None
                        ),
                        "worker_exit_code": state[0].returncode,
                    }
        except BaseException:
            _terminate_workers([state[0] for state in states.values()])
            raise
        finally:
            _terminate_workers([state[0] for state in states.values()])

    return SearchResults(
        {source: gathered.get(source, []) for source in sources},
        errors=errors,
        runtime=runtime,
    )


def _parse_date(value, field_name: str) -> date | None:
    """Parse a YYYY-MM-DD string (or pass through date/None) for the post-filter."""
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field_name} must be YYYY-MM-DD, got {value!r}") from e


def _filter_by_date_range(
    papers: list[dict],
    start_date: date | None,
    end_date: date | None,
) -> list[dict]:
    """Keep records whose known date interval overlaps the requested interval."""
    if not start_date and not end_date:
        return papers
    kept: list[dict] = []
    for p in papers:
        pub_str = p.get("publication_date")
        if not pub_str:
            kept.append(p)
            continue
        precision = p.get("date_precision") or infer_date_precision(pub_str)
        try:
            if precision == "day":
                lower = upper = date.fromisoformat(pub_str)
            elif precision == "month":
                lower = date.fromisoformat(f"{pub_str}-01")
                upper = date(
                    lower.year, lower.month, monthrange(lower.year, lower.month)[1]
                )
            elif precision == "year":
                year = int(pub_str)
                lower, upper = date(year, 1, 1), date(year, 12, 31)
            else:
                kept.append(p)
                continue
        except (TypeError, ValueError):
            kept.append(p)
            continue
        if start_date and upper < start_date:
            continue
        if end_date and lower > end_date:
            continue
        kept.append(p)
    return kept


def build_report_envelope(
    results: SearchResults,
    queries: list[str],
    *,
    start_year: int,
    end_year: int,
    min_score: int | None = None,
    enrich_citations: bool = False,
) -> dict:
    """Build the single structured representation used by JSON and text output."""
    from postprocess import dedup, rank

    per_source = {source: len(papers) for source, papers in results.items()}
    enrichment_errors: list[dict] = []
    citations_enriched = 0
    if enrich_citations:
        from enrich import enrich_citations as fill_citations

        flat_papers = [paper for papers in results.values() for paper in papers]
        citations_enriched = fill_citations(flat_papers, enrichment_errors)
    merged = dedup(results)
    ranked, dropped = rank(merged, queries, min_score=min_score)
    status_counts: dict[str, int] = {}
    for paper in ranked:
        status = str(paper.get("publication_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request": {
            "queries": list(queries),
            "start_year": start_year,
            "end_year": end_year,
            "min_score": min_score,
        },
        "papers": {source: list(papers) for source, papers in results.items()},
        "errors": {source: list(items) for source, items in results.errors.items()},
        "enrichment_errors": enrichment_errors,
        "runtime": {
            source: dict(items)
            for source, items in getattr(results, "runtime", {}).items()
        },
        "merged_ranked_papers": ranked,
        "stats": {
            "per_source_hits": per_source,
            "unique_papers": len(merged),
            "duplicates_merged": sum(per_source.values()) - len(merged),
            "dropped_below_min_score": dropped,
            "publication_status_counts": status_counts,
            "citations_enriched": citations_enriched,
        },
    }


def search_papers(
    query: str | list[str] | tuple[str, ...],
    start_year: int,
    end_year: int,
    max_results: int = DEFAULT_MAX_RESULTS,
    sources: list[str] | None = None,
    parallel: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
    source_options: dict[str, dict] | None = None,
) -> SearchResults:
    """Search for papers across multiple academic sources.

    Args:
        query: Search query string.
        start_year: Filter papers published from this year (used in source queries).
        end_year: Filter papers published up to this year (used in source queries).
        max_results: Maximum number of papers to return per source.
        sources: List of source names to search. Defaults to the stable
            OpenAlex, OpenReview, and Crossref connectors.
            Valid values: arxiv, dblp, open_alex, openreview,
            semantic_scholar, crossref.
        parallel: Whether to query sources in parallel (default: True).
        start_date: Optional YYYY-MM-DD lower bound applied as a post-filter to all
            returned papers (finer-grained than start_year). Papers without a
            known date interval overlaps the requested bounds; unknown dates are kept.
        end_date: Optional YYYY-MM-DD upper bound applied as a post-filter (inclusive).
        source_options: Optional per-source options. OpenReview accepts
            ``venues``, ``mode``, ``api_version``, ``status``, and
            ``scan_limit_per_venue``.

    Returns:
        Dictionary mapping source name to list of paper dictionaries.
        Each paper dict contains: title, authors, year, abstract, url,
        venue, citation fields, publication date/status fields, source, and IDs.
    """
    if (
        not isinstance(start_year, int)
        or isinstance(start_year, bool)
        or start_year <= 0
    ):
        raise ValueError("start_year must be a positive integer")
    if not isinstance(end_year, int) or isinstance(end_year, bool) or end_year <= 0:
        raise ValueError("end_year must be a positive integer")
    if start_year > end_year:
        raise ValueError("start_year must be <= end_year")
    if (
        not isinstance(max_results, int)
        or isinstance(max_results, bool)
        or max_results < 0
    ):
        raise ValueError("max_results must be a non-negative integer")

    sources = list(dict.fromkeys(sources or DEFAULT_SOURCES))
    invalid = set(sources) - set(ALL_SOURCES)
    if invalid:
        raise ValueError(f"Unknown sources: {invalid}. Valid: {ALL_SOURCES}")
    # Multi-query union: every query runs against every source; workers retain
    # query ranks and fuse all candidates before applying the source limit.
    raw_queries = query if isinstance(query, (list, tuple)) else [query]
    queries = [q.strip() for q in raw_queries if isinstance(q, str) and q.strip()]
    if not queries:
        raise ValueError("query must be a non-empty string or list of strings")

    if source_options is not None and not isinstance(source_options, dict):
        raise ValueError("source_options must be a mapping")
    for source, options in (source_options or {}).items():
        if source not in sources:
            raise ValueError(f"source_options contains unselected source {source!r}")
        if not isinstance(options, dict):
            raise TypeError(f"source_options[{source!r}] must be a mapping")
        unknown = set(options) - SOURCE_SPECS[source].options
        if unknown:
            raise ValueError(f"unknown {source} source options: {sorted(unknown)}")
    openreview_options = (source_options or {}).get("openreview", {})
    if openreview_options:
        scan_limit = openreview_options.get("scan_limit_per_venue", 500)
        if (
            not isinstance(scan_limit, int)
            or isinstance(scan_limit, bool)
            or scan_limit <= 0
        ):
            raise ValueError(
                "openreview scan_limit_per_venue must be a positive integer"
            )
        if openreview_options.get("api_version", "v2") not in {"v1", "v2"}:
            raise ValueError("openreview api_version must be 'v1' or 'v2'")
        if openreview_options.get("status", "accepted") not in {"accepted", "all"}:
            raise ValueError("openreview status must be 'accepted' or 'all'")
    openalex_options = (source_options or {}).get("open_alex", {})
    if openalex_options.get("search_mode", "lexical") not in {
        "lexical",
        "semantic",
    }:
        raise ValueError("open_alex search_mode must be 'lexical' or 'semantic'")
    arxiv_options = (source_options or {}).get("arxiv", {})
    if arxiv_options.get("query_mode", "balanced") not in {"balanced", "strict"}:
        raise ValueError("arxiv query_mode must be 'balanced' or 'strict'")

    start_d = _parse_date(start_date, "start_date")
    end_d = _parse_date(end_date, "end_date")
    if start_d and end_d and start_d > end_d:
        raise ValueError(f"start_date {start_d} is after end_date {end_d}")

    validate_environment(sources)
    # ID-form queries resolve directly against their authoritative registry and
    # bypass keyword workers entirely; pure-ID runs make zero keyword requests.
    id_identifiers, keyword_queries = classify_queries(queries)
    if keyword_queries:
        results = _run_source_workers(
            sources,
            keyword_queries,
            start_year,
            end_year,
            max_results,
            parallel,
            source_options=source_options,
        )
    else:
        results = SearchResults(
            {source: [] for source in sources},
            errors={source: [] for source in sources},
            runtime={source: {} for source in sources},
        )

    # Date post-filtering runs before ID resolution so that identifier lookups
    # bypass it: an ID query means "fetch this paper", not "filter by date".
    if start_d or end_d:
        results = SearchResults(
            {s: _filter_by_date_range(ps, start_d, end_d) for s, ps in results.items()},
            errors=getattr(results, "errors", {}),
            runtime=getattr(results, "runtime", {}),
        )

    if id_identifiers:
        resolve_identifiers(results, id_identifiers)

    return results


if __name__ == "__main__":
    from cli import main

    raise SystemExit(main(search_papers, build_report_envelope))

# Example usage:
# python search_papers.py --query "data efficacy for LM training" --start-year 2024 --end-year 2026 --max-papers 20
# python search_papers.py --query "transformers" --start-year 2023 --end-year 2025 --sources arxiv semantic_scholar
