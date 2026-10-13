import json
import subprocess
import sys
from pathlib import Path

from reporting import render_markdown


def sample_report():
    paper = {
        "title": "A | Reliable Paper",
        "authors": ["Ada Lovelace"],
        "year": 2025,
        "abstract": "",
        "url": "https://example.test/paper",
        "venue": "ICLR",
        "citation_count": 7,
        "citation_source": "open_alex",
        "publication_date": "2025-01-02",
        "date_precision": "day",
        "publication_status": "accepted",
        "status_source": "openreview",
        "source": "open_alex",
        "doi": "10/test",
        "arxiv_id": None,
        "found_in": ["open_alex", "openreview"],
        "relevance_score": 2,
        "is_survey": False,
    }
    return {
        "generated_at": "2026-08-15T00:00:00+00:00",
        "request": {
            "queries": ["reliable paper"],
            "start_year": 2024,
            "end_year": 2026,
        },
        "papers": {"open_alex": [paper]},
        "errors": {"open_alex": []},
        "merged_ranked_papers": [paper],
        "stats": {
            "per_source_hits": {"open_alex": 1},
            "unique_papers": 1,
            "duplicates_merged": 0,
            "dropped_below_min_score": 0,
            "publication_status_counts": {"accepted": 1},
        },
    }


def test_markdown_report_contains_full_tables_and_summary_contract():
    rendered = render_markdown(sample_report())
    assert "A \\| Reliable Paper" in rendered
    for heading in (
        "## All results",
        "### 1. Overview",
        "### 2. Trends",
        "### 3. Key themes",
        "### 4. Keywords frequency",
        "### 5. Most cited by accepted paper",
        "### 6. Most cited by first author",
        "### 7. Recommendations for reading",
    ):
        assert heading in rendered
    assert "| 1 | Ada Lovelace | 1 | 7 |" in rendered


def test_display_venue_maps_openreview_ids_and_passes_free_text_through():
    from reporting import display_venue

    assert display_venue("ICLR.cc/2025/Conference") == "ICLR 2025"
    assert display_venue("NeurIPS.cc/2024/Conference") == "NeurIPS 2024"
    assert display_venue("thecvf.com/CVPR/2024/Conference") == "CVPR 2024"
    assert display_venue("robot-learning.org/CoRL/2025/Conference") == "CoRL 2025"
    assert display_venue("EMNLP/2023/Conference") == "EMNLP 2023"
    assert (
        display_venue("Proceedings of the AAAI Conference on Artificial Intelligence")
        == "Proceedings of the AAAI Conference on Artificial Intelligence"
    )
    assert display_venue("arXiv") == "arXiv"
    assert display_venue("") == ""
    assert display_venue(None) == ""


def test_markdown_uses_display_venue_in_tables():
    report = sample_report()
    report["merged_ranked_papers"][0]["venue"] = "ICLR.cc/2025/Conference"
    rendered = render_markdown(report)
    assert "| ICLR 2025 |" in rendered
    assert "ICLR.cc/2025/Conference" not in rendered


def test_markdown_aggregates_repeated_diagnostics():
    report = sample_report()
    report["errors"]["openreview"] = [
        {
            "query": None,
            "type": "CandidateScanTruncated",
            "message": f"venue ICLR.cc/{year}/Conference scan stopped after 500 submissions",
        }
        for year in range(2020, 2033)
    ]
    rendered = render_markdown(report)
    assert rendered.count("### OpenReview") == 1
    assert "`CandidateScanTruncated` ×13" in rendered
    assert "… and 8 more" in rendered


def test_markdown_collapses_identical_diagnostics():
    report = sample_report()
    report["errors"]["semantic_scholar"] = [
        {
            "query": "some query",
            "type": "AnonymousRateLimitError",
            "message": "Semantic Scholar anonymous access was rate-limited (HTTP 429).",
        }
    ] * 2
    rendered = render_markdown(report)
    assert "`AnonymousRateLimitError` ×2" in rendered
    assert rendered.count("Semantic Scholar anonymous access was rate-limited") == 1


def test_markdown_shows_enrichment_stats_and_errors():
    report = sample_report()
    report["stats"]["citations_enriched"] = 3
    report["enrichment_errors"] = [
        {
            "query": None,
            "type": "CitationEnrichmentError",
            "message": "OpenAlex citation lookup failed: network down",
        }
    ]
    rendered = render_markdown(report)
    assert "Citation counts filled via OpenAlex: 3." in rendered
    assert "### Citation enrichment (OpenAlex)" in rendered
    assert "[CitationEnrichmentError] OpenAlex citation lookup failed" in rendered


def test_cli_writes_non_overwriting_markdown_report_end_to_end(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "search_papers.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--query",
            "test query",
            "--start-year",
            "2025",
            "--end-year",
            "2026",
            "--max-papers",
            "0",
            "--sources",
            "arxiv",
            "--format",
            "markdown",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    reports = list((tmp_path / "paper-search-reports").glob("*.md"))
    assert len(reports) == 1
    assert "## All results" in result.stdout
    assert f"report saved: {reports[0]}" in result.stderr
    assert reports[0].read_text(encoding="utf-8") == result.stdout


def test_cli_writes_run_summary_and_stderr_log(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "search_papers.py"
    log_dir = tmp_path / "logs"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--query",
            "test query",
            "--start-year",
            "2025",
            "--end-year",
            "2026",
            "--max-papers",
            "0",
            "--sources",
            "arxiv",
            "--no-save-report",
            "--log-dir",
            str(log_dir),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    run_files = list(log_dir.glob("**/run.json"))
    stderr_files = list(log_dir.glob("**/stderr.log"))
    assert len(run_files) == 1
    assert len(stderr_files) == 1
    summary = json.loads(run_files[0].read_text(encoding="utf-8"))
    assert summary["status"] == "success"
    assert summary["request"]["queries"] == ["test query"]
    assert summary["argv"][0] == sys.executable
    assert summary["argv"][1] == str(script)
    assert summary["request"]["max_papers"] == 0
    assert summary["sources"]["arxiv"]["duration_seconds"] is not None
    assert summary["report_path"] is None
    assert "[arxiv] started" in stderr_files[0].read_text(encoding="utf-8")
    assert f"run log saved: {run_files[0]}" in result.stderr


def test_cli_anchors_artifacts_to_git_root(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "search_papers.py"
    monkeypatch.delenv("PAPER_SEARCH_ROOT", raising=False)
    repo = tmp_path / "repo"
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--query",
            "test query",
            "--start-year",
            "2025",
            "--end-year",
            "2026",
            "--max-papers",
            "0",
            "--sources",
            "arxiv",
            "--format",
            "markdown",
        ],
        cwd=nested,
        text=True,
        capture_output=True,
        check=True,
    )
    reports = list((repo / "paper-search-reports").glob("*.md"))
    run_files = list((repo / "paper-search-logs").glob("**/run.json"))
    assert len(reports) == 1
    assert len(run_files) == 1
    assert not (nested / "paper-search-reports").exists()
    assert f"report saved: {reports[0]}" in result.stderr


def test_cli_can_disable_run_logging(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "search_papers.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--query",
            "test query",
            "--start-year",
            "2025",
            "--end-year",
            "2026",
            "--max-papers",
            "0",
            "--sources",
            "arxiv",
            "--no-save-report",
            "--no-log",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    assert not (tmp_path / "paper-search-logs").exists()


def test_cli_records_enrich_citations_flag_in_run_log(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "search_papers.py"
    log_dir = tmp_path / "logs"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--query",
            "test query",
            "--start-year",
            "2025",
            "--end-year",
            "2026",
            "--max-papers",
            "0",
            "--sources",
            "arxiv",
            "--enrich-citations",
            "--no-save-report",
            "--log-dir",
            str(log_dir),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    run_files = list(log_dir.glob("**/run.json"))
    assert len(run_files) == 1
    summary = json.loads(run_files[0].read_text(encoding="utf-8"))
    assert summary["request"]["enrich_citations"] is True
    assert summary["status"] == "success"
