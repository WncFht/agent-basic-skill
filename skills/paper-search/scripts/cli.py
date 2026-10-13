"""Command-line interface for the paper-search orchestrator."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from reporting import display_venue, render_markdown, write_markdown_report
from run_logging import RunLogger
from source_registry import API_SOURCES, DEFAULT_MAX_RESULTS, DEFAULT_SOURCES


def _citation_text(paper: dict) -> str:
    count = paper.get("citation_count")
    if count is None:
        return "N/A"
    source = paper.get("citation_source")
    return f"{count} ({source})" if source else str(count)


def _status_text(paper: dict) -> str:
    status = paper.get("publication_status") or "unknown"
    source = paper.get("status_source")
    return f"{status} ({source})" if source else str(status)


def render_text(report: dict, raw: bool = False) -> str:
    lines = []
    if raw:
        total = 0
        for source, papers in report["papers"].items():
            lines.extend(
                ["", "=" * 60, f"  {source}: {len(papers)} papers found", "=" * 60]
            )
            for index, paper in enumerate(papers, 1):
                authors = ", ".join((paper.get("authors") or [])[:3])
                if len(paper.get("authors") or []) > 3:
                    authors += "..."
                lines.extend(
                    [
                        f"  [{index}] {paper.get('title', '')}",
                        f"      Authors: {authors}",
                        (
                            f"      Year: {paper.get('year')}  Citations: {_citation_text(paper)}  "
                            f"Status: {_status_text(paper)}  Venue: {display_venue(paper.get('venue', ''))}"
                        ),
                        f"      URL: {paper.get('url', '')}",
                        "",
                    ]
                )
            total += len(papers)
        lines.append(f"\nTotal: {total} papers from {len(report['papers'])} sources.")
        return "\n".join(lines).lstrip("\n") + "\n"

    stats = report["stats"]
    papers = report["merged_ranked_papers"]
    lines.append(
        "per-source hits: "
        + ", ".join(
            f"{source}={count}" for source, count in stats["per_source_hits"].items()
        )
    )
    lines.append(
        f"unique papers: {stats['unique_papers']} "
        f"({stats['duplicates_merged']} cross-source duplicate records merged)"
    )
    if stats["dropped_below_min_score"]:
        lines.append(
            f"DROPPED {stats['dropped_below_min_score']} paper(s) below the minimum score"
        )
    lines.append("=" * 60)
    for index, paper in enumerate(papers, 1):
        tag = " [survey]" if paper.get("is_survey") else ""
        sources = ",".join(paper.get("found_in") or [])
        identifiers = " ".join(
            value
            for value in (
                f"doi:{paper['doi']}" if paper.get("doi") else "",
                f"arXiv:{paper['arxiv_id']}" if paper.get("arxiv_id") else "",
            )
            if value
        )
        authors = ", ".join((paper.get("authors") or [])[:3])
        if len(paper.get("authors") or []) > 3:
            authors += "..."
        lines.extend(
            [
                f"  [{index}] (score {paper.get('relevance_score', 0)}){tag} {paper.get('title', '')}",
                f"      Authors: {authors}",
                (
                    f"      Year: {paper.get('year')}  Citations: {_citation_text(paper)}  "
                    f"Status: {_status_text(paper)}  Venue: {display_venue(paper.get('venue', ''))}"
                ),
                f"      Sources: {sources}"
                + (f"  {identifiers}" if identifiers else ""),
                f"      URL: {paper.get('url', '')}",
                "",
            ]
        )
    lines.append(
        f"Total: {len(papers)} unique papers (ranked; surveys sunk to the bottom)."
    )
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search papers across multiple academic sources"
    )
    parser.add_argument("--query", default=None)
    parser.add_argument(
        "--queries", default=None, help="Pipe-separated multi-query union"
    )
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--max-papers", type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument("--sources", nargs="+", choices=API_SOURCES)
    parser.add_argument("--openreview-venues", nargs="+", default=None)
    parser.add_argument("--openreview-api-version", choices=("v1", "v2"), default="v2")
    parser.add_argument(
        "--openreview-mode",
        choices=("auto", "cache", "remote"),
        default="auto",
        help="cache answers from the local SQLite cache; remote always hits the API",
    )
    parser.add_argument(
        "--openreview-status", choices=("accepted", "all"), default="accepted"
    )
    parser.add_argument("--openreview-scan-limit-per-venue", type=int, default=500)
    parser.add_argument(
        "--openalex-search-mode", choices=("lexical", "semantic"), default="lexical"
    )
    parser.add_argument(
        "--arxiv-query-mode", choices=("balanced", "strict"), default="balanced"
    )
    parser.add_argument("--dblp-enrich-abstracts", action="store_true")
    parser.add_argument("--no-parallel", action="store_true")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument(
        "--raw", action="store_true", help="Legacy per-source text view"
    )
    parser.add_argument(
        "--json", action="store_true", help="Compatibility alias for --format json"
    )
    parser.add_argument(
        "--format", choices=("text", "markdown", "json"), default="text"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write selected format without overwriting",
    )
    parser.add_argument(
        "--report-path", type=Path, default=None, help="Explicit Markdown report path"
    )
    parser.add_argument("--no-save-report", action="store_true")
    parser.add_argument(
        "--no-log", action="store_true", help="Disable run.json and stderr.log"
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Base directory for run logs (default: <artifact-root>/paper-search-logs)",
    )
    parser.add_argument("--min-score", type=int, default=None)
    parser.add_argument(
        "--enrich-citations",
        action="store_true",
        help="Fill missing citation counts via batched OpenAlex DOI lookups",
    )
    return parser


def main(search_fn=None, build_report_fn=None) -> int:
    if search_fn is None or build_report_fn is None:
        from search_papers import build_report_envelope, search_papers

        search_fn = search_fn or search_papers
        build_report_fn = build_report_fn or build_report_envelope

    parser = _parser()
    args = parser.parse_args()
    if not args.query and not args.queries:
        parser.error("one of --query / --queries is required")
    if args.query and args.queries:
        parser.error("--query and --queries are mutually exclusive")
    if args.json and args.format != "text":
        parser.error("--json cannot be combined with --format")
    if args.raw and (args.json or args.format != "text"):
        parser.error("--raw is only compatible with text output")

    queries = (
        [query.strip() for query in args.queries.split("|") if query.strip()]
        if args.queries
        else [args.query]
    )
    source_options = {}
    if (
        args.openreview_venues
        or args.openreview_api_version != "v2"
        or args.openreview_mode != "auto"
        or args.openreview_status != "accepted"
        or args.openreview_scan_limit_per_venue != 500
    ):
        source_options["openreview"] = {
            "venues": args.openreview_venues,
            "api_version": args.openreview_api_version,
            "mode": args.openreview_mode,
            "status": args.openreview_status,
            "scan_limit_per_venue": args.openreview_scan_limit_per_venue,
        }
    if args.openalex_search_mode != "lexical":
        source_options["open_alex"] = {"search_mode": args.openalex_search_mode}
    if args.arxiv_query_mode != "balanced":
        source_options["arxiv"] = {"query_mode": args.arxiv_query_mode}
    if args.dblp_enrich_abstracts:
        source_options["dblp"] = {"enrich_abstracts": True}

    logger = None
    if not args.no_log:
        try:
            logger = RunLogger(args.log_dir)
        except OSError as exc:
            print(f"run logging unavailable: {exc}", file=sys.stderr)
    report = None
    report_path = None
    exception = None
    exit_code = 0
    stderr_context = (
        contextlib.redirect_stderr(logger.tee) if logger else contextlib.nullcontext()
    )
    try:
        with stderr_context:
            results = search_fn(
                query=queries,
                start_year=args.start_year,
                end_year=args.end_year,
                max_results=args.max_papers,
                sources=args.sources,
                parallel=not args.no_parallel,
                start_date=args.start_date,
                end_date=args.end_date,
                source_options=source_options or None,
            )
            report = build_report_fn(
                results,
                queries,
                start_year=args.start_year,
                end_year=args.end_year,
                min_score=args.min_score,
                enrich_citations=args.enrich_citations,
            )
            report["request"].update(
                {
                    "max_papers": args.max_papers,
                    "sources": list(args.sources or DEFAULT_SOURCES),
                    "parallel": not args.no_parallel,
                    "start_date": args.start_date,
                    "end_date": args.end_date,
                    "source_options": source_options or {},
                    "enrich_citations": args.enrich_citations,
                }
            )

            output_format = "json" if args.json else args.format
            rendered = (
                json.dumps(report, ensure_ascii=False, indent=2) + "\n"
                if output_format == "json"
                else render_markdown(report)
                if output_format == "markdown"
                else render_text(report, raw=args.raw)
            )
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8") as handle:
                    handle.write(rendered)
            else:
                sys.stdout.write(rendered)

            if not args.no_save_report:
                if (
                    output_format == "markdown"
                    and args.output
                    and args.report_path is None
                ):
                    report_path = args.output
                else:
                    report_path = write_markdown_report(report, output=args.report_path)
            if report_path:
                print(f"report saved: {report_path}", file=sys.stderr)
    except BaseException as exc:
        exception = exc
        exit_code = 130 if isinstance(exc, KeyboardInterrupt) else 1
        raise
    finally:
        if logger:
            try:
                summary_path = logger.write_summary(
                    argv=[sys.executable, *sys.argv],
                    report=report,
                    report_path=report_path,
                    exit_code=exit_code,
                    exception=exception,
                )
            except OSError as exc:
                print(f"could not finalize run log: {exc}", file=sys.stderr)
            else:
                if exception is None:
                    print(f"run log saved: {summary_path}", file=sys.stderr)
            finally:
                logger.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
