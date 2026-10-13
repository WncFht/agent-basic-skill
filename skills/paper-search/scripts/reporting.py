"""Deterministic text and Markdown rendering for paper-search reports."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from _artifacts import artifact_root

_SOURCE_LABELS = {
    "semantic_scholar": "Semantic Scholar",
    "open_alex": "OpenAlex",
    "arxiv": "arXiv",
    "openreview": "OpenReview",
    "crossref": "Crossref",
    "dblp": "DBLP",
}

# OpenReview venue IDs ("ICLR.cc/2025/Conference") are internal identifiers;
# display form is "<Org> <Year>" with domain labels stripped.
_VENUE_ID_RE = re.compile(r"^(?:[^/]+/)*(?P<org>[^/]+)/(?P<year>20\d{2})/\w+$")
_VENUE_DOMAIN_TLDS = {"cc", "org", "com", "net", "web"}

# Rendered diagnostics list at most this many messages per (source, type)
# group; the full list stays in the JSON envelope and stderr.log.
MAX_LISTED_DIAGNOSTICS = 5

_TITLE_STOP = {
    "about",
    "analysis",
    "approach",
    "based",
    "from",
    "learning",
    "method",
    "model",
    "models",
    "large",
    "over",
    "exploring",
    "paper",
    "study",
    "that",
    "their",
    "through",
    "towards",
    "using",
    "with",
}


def _md(value) -> str:
    return str(value or "").replace("\n", " ").replace("|", "\\|").strip()


def _url(value) -> str:
    return str(value or "").replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def _source_text(paper: dict) -> str:
    sources = paper.get("found_in") or [paper.get("source")]
    return ", ".join(
        _SOURCE_LABELS.get(source, str(source)) for source in sources if source
    )


def display_venue(venue) -> str:
    """Map internal venue IDs to a readable form; pass anything else through."""
    raw = str(venue or "").strip()
    match = _VENUE_ID_RE.match(raw)
    if not match:
        return raw
    org = match.group("org")
    if "." in org:
        labels = org.split(".")
        if labels[-1].casefold() in _VENUE_DOMAIN_TLDS:
            org = labels[0]
    return f"{org} {match.group('year')}"


def _citation_text(paper: dict) -> str:
    count = paper.get("citation_count")
    return "N/A" if count is None else str(count)


def _title_tokens(title: str) -> list[str]:
    normalized = str(title or "").casefold()
    tokens = re.findall(r"[a-z0-9][a-z0-9-]{3,}|[\u3400-\u9fff]{2,}", normalized)
    return [token for token in tokens if token not in _TITLE_STOP]


def _keyword_counts(papers: list[dict]) -> Counter:
    counts: Counter = Counter()
    for paper in papers:
        counts.update(set(_title_tokens(paper.get("title", ""))))
    return counts


def _paper_table(papers: list[dict]) -> list[str]:
    lines = [
        "| # | Title | Date | Venue | Citations | Score | Sources |",
        "|---:|---|---|---|---:|---:|---|",
    ]
    for index, paper in enumerate(papers, 1):
        title = _md(paper.get("title"))
        if paper.get("is_survey"):
            title = f"[survey] {title}"
        url = _url(paper.get("url"))
        rank_cell = f"[{index}]({url})" if url else str(index)
        date_text = paper.get("publication_date") or paper.get("year") or "N/A"
        lines.append(
            "| "
            + " | ".join(
                [
                    rank_cell,
                    title,
                    _md(date_text),
                    _md(display_venue(paper.get("venue") or "N/A")),
                    _citation_text(paper),
                    str(paper.get("relevance_score", 0)),
                    _md(_source_text(paper)),
                ]
            )
            + " |"
        )
    return lines


def _summary_lines(report: dict) -> list[str]:
    request = report["request"]
    papers = report["merged_ranked_papers"]
    stats = report["stats"]
    queries = "; ".join(request["queries"])
    lines = [
        "## Summary of all searched results",
        "",
        "### 1. Overview",
        "",
        (
            f"Queries: {_md(queries)}. Year range: {request['start_year']}-{request['end_year']}. "
            f"The search returned {len(papers)} ranked unique papers from "
            f"{sum(1 for value in stats['per_source_hits'].values() if value)} sources with hits."
        ),
        "",
        "### 2. Trends",
        "",
    ]

    year_counts = Counter(str(paper.get("year") or "unknown") for paper in papers)
    venue_counts = Counter(
        display_venue(str(paper.get("venue"))) for paper in papers if paper.get("venue")
    )
    recurring_authors = Counter(
        str((paper.get("authors") or [""])[0])
        for paper in papers
        if paper.get("authors")
    )
    year_text = (
        ", ".join(f"{year}: {count}" for year, count in year_counts.most_common(5))
        or "none"
    )
    venue_text = (
        ", ".join(f"{venue}: {count}" for venue, count in venue_counts.most_common(5))
        or "none"
    )
    author_text = (
        ", ".join(
            f"{author}: {count}"
            for author, count in recurring_authors.most_common(5)
            if count > 1
        )
        or "no recurring first author"
    )
    lines.extend(
        [
            (
                f"Year distribution: {_md(year_text)}. Dominant venues: {_md(venue_text)}. "
                f"Recurring first authors: {_md(author_text)}."
            ),
            "",
            "### 3. Key themes",
            "",
        ]
    )

    keywords = _keyword_counts(papers)
    for keyword, _count in keywords.most_common(6):
        representatives = [
            index
            for index, paper in enumerate(papers, 1)
            if keyword in _title_tokens(paper.get("title", ""))
        ][:3]
        numbers = ", ".join(f"[{index}]" for index in representatives)
        lines.append(
            f"- `{_md(keyword)}`: recurring title-level cluster represented by {numbers}."
        )
    if not keywords:
        lines.append("No stable title-level keyword cluster was available.")

    lines.extend(
        [
            "",
            "### 4. Keywords frequency",
            "",
            "| Keyword | Count |",
            "|---|---:|",
        ]
    )
    for keyword, count in keywords.most_common(5):
        lines.append(f"| {_md(keyword)} | {count} |")
    if not keywords:
        lines.append("| N/A | 0 |")

    lines.extend(
        [
            "",
            "### 5. Most cited by accepted paper",
            "",
            "| Rank | Title | Year | Citations |",
            "|---:|---|---:|---:|",
        ]
    )
    accepted = sorted(
        (
            paper
            for paper in papers
            if paper.get("publication_status") in {"accepted", "published"}
            and paper.get("citation_count") is not None
        ),
        key=lambda paper: -int(paper["citation_count"]),
    )[:5]
    for index, paper in enumerate(accepted, 1):
        lines.append(
            f"| {index} | {_md(paper.get('title'))} | {paper.get('year') or 'N/A'} | "
            f"{paper['citation_count']} |"
        )
    if not accepted:
        lines.append(
            "| - | No accepted/published paper with a known citation count | - | - |"
        )

    author_totals: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    for paper in papers:
        authors = paper.get("authors") or []
        citations = paper.get("citation_count")
        if not authors or citations is None:
            continue
        author_totals[str(authors[0])][0] += 1
        author_totals[str(authors[0])][1] += int(citations)
    top_authors = sorted(
        author_totals.items(),
        key=lambda item: (-item[1][1], -item[1][0], item[0].casefold()),
    )[:5]
    lines.extend(
        [
            "",
            "### 6. Most cited by first author",
            "",
            "| Rank | Author | Papers in set | Total citations |",
            "|---:|---|---:|---:|",
        ]
    )
    for index, (author, (count, citations)) in enumerate(top_authors, 1):
        lines.append(f"| {index} | {_md(author)} | {count} | {citations} |")
    if not top_authors:
        lines.append("| - | N/A | 0 | 0 |")

    selected = list(enumerate(papers[:5], 1))
    selected.sort(key=lambda item: (item[1].get("year") or 9999, item[0]))
    lines.extend(["", "### 7. Recommendations for reading", ""])
    for original_rank, paper in selected:
        lines.append(
            f"- [{original_rank}] {_md(paper.get('title'))}: chronological reading candidate; "
            f"score {paper.get('relevance_score', 0)}, sources {_md(_source_text(paper))}."
        )
    if not selected:
        lines.append("No papers were available for a reading path.")
    return lines


def render_markdown(report: dict) -> str:
    stats = report["stats"]
    papers = report["merged_ranked_papers"]
    hit_text = ", ".join(
        f"{source}={count}" for source, count in stats["per_source_hits"].items()
    )
    lines = [
        "# Paper Search Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        (
            f"Per-source hits: {hit_text}. {stats['unique_papers']} unique papers; "
            f"{stats['duplicates_merged']} duplicate records merged."
        ),
    ]
    dropped = stats.get("dropped_below_min_score", 0)
    if dropped:
        lines.append(f"Dropped below minimum score: {dropped}.")
    if stats.get("citations_enriched"):
        lines.append(
            f"Citation counts filled via OpenAlex: {stats['citations_enriched']}."
        )
    lines.extend(["", "## All results", "", *_paper_table(papers), ""])

    diagnostic_lines = _diagnostic_lines(report)
    if diagnostic_lines:
        lines.extend(["## Source diagnostics", "", *diagnostic_lines, ""])
    lines.extend(_summary_lines(report))
    return "\n".join(lines).rstrip() + "\n"


def _diagnostic_lines(report: dict) -> list[str]:
    """Render diagnostics grouped by source and type.

    Rendering aggregates; the JSON envelope keeps every item verbatim. Exact
    duplicate messages collapse, and long groups are capped at
    MAX_LISTED_DIAGNOSTICS entries with an "... and N more" line.
    """
    lines: list[str] = []
    errors = report.get("errors") or {}
    for source, items in errors.items():
        if not items:
            continue
        lines.extend([f"### {_SOURCE_LABELS.get(source, source)}", ""])
        grouped: dict[str, list[dict]] = {}
        for item in items:
            grouped.setdefault(str(item.get("type") or "Unknown"), []).append(item)
        for diagnostic_type, group in grouped.items():
            unique_messages: list[str] = []
            for item in group:
                message = f"query={item.get('query')!r}: {item.get('message')}"
                if message not in unique_messages:
                    unique_messages.append(message)
            count_suffix = f" ×{len(group)}" if len(group) > 1 else ""
            lines.append(f"- `{diagnostic_type}`{count_suffix}")
            shown = unique_messages[:MAX_LISTED_DIAGNOSTICS]
            for message in shown:
                lines.append(f"  - {message}")
            omitted = len(unique_messages) - len(shown)
            if omitted > 0:
                lines.append(f"  - … and {omitted} more")
        lines.append("")
    for item in report.get("enrichment_errors") or []:
        lines.extend(
            [
                "### Citation enrichment (OpenAlex)",
                "",
                "```text",
                f"[{item.get('type')}] {item.get('message')}",
                "```",
                "",
            ]
        )
    return lines


def default_report_path(queries: list[str], base_dir: Path | None = None) -> Path:
    report_dir = (base_dir or artifact_root()) / "paper-search-reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", "-".join(queries).casefold()).strip("-")
    slug = (slug or "query")[:64]
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    return report_dir / f"{timestamp}-{slug}.md"


def write_markdown_report(
    report: dict, output: Path | None = None, base_dir: Path | None = None
) -> Path:
    path = output or default_report_path(report["request"]["queries"], base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(render_markdown(report))
    return path
