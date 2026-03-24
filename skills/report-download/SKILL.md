---
name: "report-download"
description: "Use when the user asks to download A-share or Hong Kong listed company financial report PDFs, including 年报/中报/一季报/三季报, annual report, interim report, or when a stock-analysis workflow needs the latest full-year report PDF."
---

# Report Download Skill

Find and download A-share or Hong Kong listed company report PDFs with official sources first:
- A股：`CNINFO / 巨潮资讯`
- 港股：`HKEXnews`
- 失败时再回退到 `stockn.xueqiu.com` 和 `notice.10jqka.com.cn`

## When to use
- The user asks to 下载财报、下载年报、下载中报、annual report download、financial report PDF.
- Another stock-analysis skill needs the latest annual report PDF before parsing.
- The user provides only a stock code/year/report type and wants a local PDF path.

## Skill path

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export STOCK_SKILL_WORKSPACE_ROOT="${STOCK_SKILL_WORKSPACE_ROOT:-$HOME/Desktop/src/skill-runs}"
export REPORT_DOWNLOAD_ROOT="$CODEX_HOME/skills/report-download"
export REPORT_DOWNLOAD_CLI="$REPORT_DOWNLOAD_ROOT/scripts/search_and_download_report.py"
export REPORT_DOWNLOAD_SAVE_DIR="${REPORT_DOWNLOAD_SAVE_DIR:-$STOCK_SKILL_WORKSPACE_ROOT/report-download}"
```

## Preferred workflow
1. Parse `stock_code`, optional `year`, optional `report_type`.
2. Prefer the bundled helper script to search and download in one step:

```bash
uv run --project "$REPORT_DOWNLOAD_ROOT" python "$REPORT_DOWNLOAD_CLI" \
  --stock-code "600887" \
  --year "2024" \
  --report-type "年报" \
  --save-dir "$REPORT_DOWNLOAD_SAVE_DIR"
```

3. Source order:
   - A股：先查 `CNINFO / 巨潮资讯` 官方公告，再退到搜索引擎结果与第三方镜像。
   - 港股：先查 `HKEXnews` 官方 PDF，再退到雪球 / 同花顺。
4. Only accept URLs from these PDF hosts:
   - `static.cninfo.com.cn`
   - `www1.hkexnews.hk`
   - `stockn.xueqiu.com`
   - `notice.10jqka.com.cn`
5. Prefer complete reports and exclude results that look like 摘要、审计报告、公告、更正、补充、ESG、summary, auditor, dividend.
6. Report the final local file path, source URL, stock code, year, report type, and file size.
7. Default download root is `~/Desktop/src/skill-runs/report-download/` unless the user explicitly asks for another location.

## Input normalization
- `600887` → `SH600887`
- `300750` → `SZ300750`
- `700` / `00700` → `00700`
- `年报` / `annual` → annual report
- `中报` / `interim` → interim report
- `一季报` / `Q1` → first-quarter report
- `三季报` / `Q3` → third-quarter report

If `year` is omitted, default to the latest likely full fiscal year:
- January to March: use `current_year - 2` for 年报
- April to December: use `current_year - 1` for 年报

## Dependencies
Prefer `uv`.

```bash
uv sync --project "$REPORT_DOWNLOAD_ROOT"
```

The helper scripts require `ddgs` and `requests`.

## Bundled scripts
- `scripts/search_and_download_report.py`: official-source-first report searcher, with CNINFO / HKEXnews priority.
- `scripts/download_report.py`: low-level downloader with retries and PDF validation.

## Success criteria
- The file downloads successfully.
- The first bytes match `%PDF-`.
- The final output is a clickable local path the user can open.
