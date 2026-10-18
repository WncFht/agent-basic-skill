from __future__ import annotations

import re

from core.models import FatalDiagnosis

RERUN_HINT_RE = re.compile(
    r"Label\(s\) may have changed|Rerun to get cross-references right"
)
WARNING_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "undefined citations",
        re.compile(r"(?:Package natbib Warning:\s*)?Citation `[^']+' .* undefined"),
    ),
    (
        "undefined references",
        re.compile(r"(?:LaTeX Warning:\s*)?Reference `[^']+' .* undefined"),
    ),
    (
        "rerun needed",
        re.compile(r"Label\(s\) may have changed|Rerun to get cross-references right"),
    ),
    (
        "headheight too small",
        re.compile(r"Package fancyhdr Warning: \\\\headheight is too small"),
    ),
    (
        "missing image descriptions",
        re.compile(
            r"possible image without description|A possible image without description",
            re.I,
        ),
    ),
)
NOISY_PRE_BIB_WARNING_LABELS = {
    "undefined citations",
    "undefined references",
    "rerun needed",
}


def summarize_warnings(
    outputs: list[str],
    *,
    suppress_labels: set[str] | None = None,
) -> tuple[str, ...]:
    suppress_labels = suppress_labels or set()
    combined = "\n".join(outputs)
    summary: list[str] = []
    matched_lines: set[str] = set()

    all_patterns = [pattern for _, pattern in WARNING_CATEGORY_PATTERNS]
    for label, pattern in WARNING_CATEGORY_PATTERNS:
        if label in suppress_labels:
            continue
        for match in pattern.finditer(combined):
            line = match.group(0).strip()
            if line and line not in matched_lines:
                matched_lines.add(line)
                summary.append(line)

    fallback_lines: list[str] = []
    for line in combined.splitlines():
        stripped = line.strip()
        if (
            "Warning:" not in stripped
            or "Underfull" in stripped
            or "Overfull" in stripped
        ):
            continue
        if any(pattern.search(stripped) for pattern in all_patterns):
            continue
        if stripped not in matched_lines:
            matched_lines.add(stripped)
            fallback_lines.append(stripped)
    summary.extend(fallback_lines[:5])
    return tuple(summary)


def summarize_final_warnings(outputs: list[str]) -> tuple[str, ...]:
    if not outputs:
        return ()
    return summarize_warnings([outputs[-1]])


def summarize_quick_warnings(
    outputs: list[str], *, has_bibtex: bool
) -> tuple[str, ...]:
    if not outputs:
        return ()
    suppress_labels = NOISY_PRE_BIB_WARNING_LABELS if has_bibtex else set()
    return summarize_warnings([outputs[-1]], suppress_labels=suppress_labels)


def extract_fatal_summary(output: str) -> tuple[str, ...]:
    summary: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("! "):
            summary.append(stripped)
        elif re.match(r"l\.\d+", stripped):
            summary.append(stripped)
        if len(summary) >= 4:
            break
    if summary:
        return tuple(summary)

    tail = [line.strip() for line in output.splitlines() if line.strip()]
    return tuple(tail[-4:])


def diagnose_fatal(output: str) -> FatalDiagnosis:
    summary = extract_fatal_summary(output)
    lowered = output.lower()

    if "missing $ inserted" in lowered:
        return FatalDiagnosis(
            code="missing-dollar",
            summary=summary,
            advice=(
                r"优先检查最近改过的 \bgsent / \zh*sent / \zhtrans / \pnote / annsummary 是否写了裸数学宏。",
                r"像 \geq、\approx、\alpha、\mathbb 这类数学命令必须包进 $...$。",
            ),
        )

    if "unicode character" in lowered and (
        "not set up for use with latex" in lowered
        or "not set up for use with pdftex" in lowered
    ):
        should_retry = any(
            token in lowered for token in ("\\end{document}", ".aux", ".out")
        )
        return FatalDiagnosis(
            code="unicode-moving-argument",
            summary=summary,
            advice=(
                "检测到 Unicode 与 pdflatex 兼容错误；高概率是中文进入了标题、目录、书签或 .aux/.out 回写链路。",
                r"检查 \title、\section、\subsection、\paragraph 等 moving arguments，避免直接写中文或 \section{\bititle{...}{...}}。",
                r"优先改用 \bipapertitle、\bisec、\bisubsec、\bipara 这类安全双语标题宏。",
            ),
            should_retry_with_aux_cleanup=should_retry,
        )

    return FatalDiagnosis(code="generic", summary=summary, advice=())


def should_rerun_latex(output: str) -> bool:
    return bool(RERUN_HINT_RE.search(output))
