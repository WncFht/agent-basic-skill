from __future__ import annotations

import re
from pathlib import Path

from core.lint_parse import (
    contains_non_ascii,
    find_annsummary_ranges,
    find_bare_math_macros,
    find_unmatched_dollars,
    line_number_at,
    parse_braced_group,
    parse_command_calls,
    parse_first_optional_arg,
    strip_comments,
    strip_tex_commands,
)
from core.models import LintIssue, LintResult
from core.workspace import (
    GENERATED_ENTRY_FILE_NAMES,
    PREAMBLE_FILE_NAME,
    STALE_GENERATED_DIR_NAMES,
)

NOTE_COMMAND_NAME = "pnote"
LEGACY_GENERATED_DIR_NAMES = ("paper_note_zh",)
BIBLIOGRAPHY_LIKE_RE = re.compile(
    r"\\begin\{thebibliography\}|\\bibliography\s*\{|\\bibliographystyle\s*\{|\\printbibliography\b"
)
LEGACY_NOTE_COMMAND_RE = re.compile(r"\\annnote(?=\s*\{)")
TYPO_NOTE_COMMAND_RE = re.compile(r"\\annote(?=\s*\{)")
SENTENCE_MACRO_NAMES = (
    "bgsent",
    "gapsent",
    "questionsent",
    "methodsent",
    "resultsent",
    "claimsent",
    "structsent",
    "relatedsent",
)
KEY_SENTENCE_MACRO_NAMES = ("keysent", "zhkeysent")
ZH_SENTENCE_MACRO_NAMES = tuple(f"zh{name}" for name in SENTENCE_MACRO_NAMES)
INLINE_TRANSLATION_MACRO_NAMES = ("zhtrans",)
FOOTNOTE_RESTRICTED_MACRO_NAMES = (
    SENTENCE_MACRO_NAMES + ZH_SENTENCE_MACRO_NAMES + KEY_SENTENCE_MACRO_NAMES
)
INLINE_TEXT_MACRO_NAMES = (
    FOOTNOTE_RESTRICTED_MACRO_NAMES + INLINE_TRANSLATION_MACRO_NAMES
)
FOOTNOTE_COMMAND_RE = re.compile(
    r"\\(footnote|footnotemark)(?=\s*(?:\{|(?:\[[^\]]*\])?\{))"
)
MOVING_ARGUMENT_COMMAND_SPECS = (
    ("title", False),
    ("part", True),
    ("chapter", True),
    ("section", True),
    ("subsection", True),
    ("subsubsection", True),
    ("paragraph", True),
    ("subparagraph", True),
)
SAFE_HEADING_MACROS = {
    "title": "bipapertitle",
    "part": "bipart",
    "chapter": "bichapter",
    "section": "bisec",
    "subsection": "bisubsec",
    "subsubsection": "bisubsubsec",
    "paragraph": "bipara",
    "subparagraph": "bisubpara",
}


def lint_moving_arguments(path: Path, text: str) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for command_name, allow_optional in MOVING_ARGUMENT_COMMAND_SPECS:
        pattern = re.compile(rf"\\{re.escape(command_name)}(?=\s*(?:\[|\{{))")
        for match in pattern.finditer(text):
            cursor = match.end()
            optional_arg = None
            if allow_optional:
                parsed_optional = parse_first_optional_arg(text, cursor)
                if parsed_optional is not None:
                    optional_arg, cursor = parsed_optional

            parsed_group = parse_braced_group(text, cursor)
            if parsed_group is None:
                continue
            main_arg, _ = parsed_group
            line = line_number_at(text, match.start())
            safe_macro_name = SAFE_HEADING_MACROS[command_name]
            has_bititle = r"\bititle" in main_arg
            has_non_ascii = contains_non_ascii(strip_tex_commands(main_arg))

            if has_bititle and (command_name == "title" or optional_arg is None):
                issues.append(
                    LintIssue(
                        path=path,
                        line=line,
                        kind="unsafe-bititle-moving-argument",
                        message=(
                            rf"检测到 \{command_name}{{\bititle{{...}}{{...}}}}；"
                            r"在 pdflatex + CJKutf8 下容易把中文写进 .aux / 书签并触发 Unicode fatal。"
                            rf" 请改用安全宏，例如 \{safe_macro_name}{{English}}{{中文}}。"
                        ),
                    )
                )

            if command_name == "title" and has_non_ascii:
                issues.append(
                    LintIssue(
                        path=path,
                        line=line,
                        kind="non-ascii-moving-argument",
                        message=(
                            rf"\{command_name} 的主参数里检测到非 ASCII 文本；"
                            r"在 pdflatex + CJKutf8 下这通常会回写到 .aux / 书签并导致编译失败。"
                            r" 请把 optional short title 保持英文，并把中文放到 \bititle / 安全双语标题宏的显示层。"
                        ),
                    )
                )

            if command_name != "title" and optional_arg is None and has_bititle:
                issues.append(
                    LintIssue(
                        path=path,
                        line=line,
                        kind="missing-short-title",
                        message=(
                            rf"\{command_name} 使用双语显示标题时缺少英文 optional short title；"
                            r"这会让 LaTeX 直接把显示标题写进目录或书签。请改用"
                            rf" \{safe_macro_name}{{English}}{{中文}} 或手写 \{command_name}[English]{{...}}。"
                        ),
                    )
                )

            if command_name != "title" and optional_arg is None and has_non_ascii:
                issues.append(
                    LintIssue(
                        path=path,
                        line=line,
                        kind="non-ascii-moving-argument",
                        message=(
                            rf"\{command_name} 的主参数里检测到非 ASCII 文本，且没有英文 optional short title；"
                            r"在 pdflatex + CJKutf8 下这通常会回写到 .aux / 书签并导致编译失败。"
                            r" 请把 optional short title 保持英文，并把中文放到 \bititle / 安全双语标题宏的显示层。"
                        ),
                    )
                )
    return issues


def is_bibliography_like_tex(text: str) -> bool:
    return bool(BIBLIOGRAPHY_LIKE_RE.search(text))


def lint_file(path: Path) -> list[LintIssue]:
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    text = strip_comments(raw_text)
    if is_bibliography_like_tex(text):
        return []
    issues: list[LintIssue] = []

    for match in LEGACY_NOTE_COMMAND_RE.finditer(text):
        issues.append(
            LintIssue(
                path=path,
                line=line_number_at(text, match.start()),
                kind="legacy-note-command",
                message=rf"不再支持 \annnote{{...}}；请改成 \{NOTE_COMMAND_NAME}{{功能|判断}}{{评}}。",
            )
        )

    for match in TYPO_NOTE_COMMAND_RE.finditer(text):
        issues.append(
            LintIssue(
                path=path,
                line=line_number_at(text, match.start()),
                kind="typo-note-command",
                message=rf"检测到拼写错误 \annote{{...}}；应使用 \{NOTE_COMMAND_NAME}{{功能|判断}}{{评}}。",
            )
        )

    _, unmatched_annsummary_lines = find_annsummary_ranges(text)
    for line in unmatched_annsummary_lines:
        issues.append(
            LintIssue(
                path=path,
                line=line,
                kind="annsummary-balance",
                message=r"\begin{annsummary} 与 \end{annsummary} 未正确配对。",
            )
        )

    for line in find_unmatched_dollars(text):
        issues.append(
            LintIssue(
                path=path,
                line=line,
                kind="unmatched-dollar",
                message=r"检测到未配对的 $ 或 $$。",
            )
        )

    for command_name in FOOTNOTE_RESTRICTED_MACRO_NAMES:
        for call in parse_command_calls(text, command_name, 1, 1):
            footnote_match = FOOTNOTE_COMMAND_RE.search(call.args[0])
            if footnote_match is None:
                continue
            footnote_command = footnote_match.group(1)
            issues.append(
                LintIssue(
                    path=path,
                    line=call.line,
                    kind="footnote-inside-sentence-macro",
                    message=(
                        rf"检测到 \{footnote_command} 被写进 \{call.name}{{...}} 内部；"
                        r"请把脚注命令移到句子功能宏外面，例如 "
                        rf"\{call.name}{{...}}\{footnote_command}{{...}}。"
                    ),
                )
            )

    for command_name in INLINE_TEXT_MACRO_NAMES:
        for call in parse_command_calls(text, command_name, 1, 1):
            for line, math_name in find_bare_math_macros(call.args[0], call.line):
                issues.append(
                    LintIssue(
                        path=path,
                        line=line,
                        kind="bare-math-macro",
                        message=(
                            rf"\{call.name}{{...}} 里出现裸数学宏 \{math_name}；"
                            r"必须包进 $...$。"
                        ),
                    )
                )

    for note_call in parse_command_calls(text, NOTE_COMMAND_NAME, 2, 3):
        if len(note_call.args) == 3:
            issues.append(
                LintIssue(
                    path=path,
                    line=note_call.line,
                    kind="legacy-pnote-arity",
                    message=(
                        rf"\{NOTE_COMMAND_NAME} 已改成两参数；"
                        r"请使用 \pnote{功能|判断}{评}，不要再在句级批注里写翻译。"
                    ),
                )
            )
            evaluation_arg = note_call.args[2]
        else:
            evaluation_arg = note_call.args[1]
        for line, command_name in find_bare_math_macros(evaluation_arg, note_call.line):
            issues.append(
                LintIssue(
                    path=path,
                    line=line,
                    kind="bare-math-macro",
                    message=(
                        rf"\{NOTE_COMMAND_NAME} 的“评”里出现裸数学宏 \{command_name}；"
                        r"必须包进 $...$。"
                    ),
                )
            )

    annsummary_ranges, _ = find_annsummary_ranges(text)
    for start, end, begin_line in annsummary_ranges:
        segment = text[start:end]
        for line, command_name in find_bare_math_macros(segment, begin_line):
            issues.append(
                LintIssue(
                    path=path,
                    line=line,
                    kind="bare-math-macro",
                    message=rf"annsummary 里出现裸数学宏 \{command_name}；必须包进 $...$。",
                )
            )

    issues.extend(lint_moving_arguments(path, text))
    return issues


def collect_tex_files(workspace: Path) -> list[Path]:
    return sorted(
        path
        for path in workspace.rglob("*.tex")
        if path.is_file()
        and path.name != PREAMBLE_FILE_NAME
        and path.name not in GENERATED_ENTRY_FILE_NAMES
        and not any(
            part in LEGACY_GENERATED_DIR_NAMES or part in STALE_GENERATED_DIR_NAMES
            for part in path.relative_to(workspace).parts
        )
    )


def lint_workspace(workspace: Path, *, tex_file: Path | None = None) -> LintResult:
    issues: list[LintIssue] = []
    tex_files = [tex_file] if tex_file is not None else collect_tex_files(workspace)
    for path in tex_files:
        issues.extend(lint_file(path))
    issues.sort(key=lambda item: (str(item.path), item.line, item.kind, item.message))
    return LintResult(
        workspace=workspace,
        checked_files=tuple(tex_files),
        issues=tuple(issues),
    )


def format_issue(issue: LintIssue, workspace: Path) -> str:
    relative_path = issue.path.relative_to(workspace).as_posix()
    return f"{relative_path}:{issue.line}: [{issue.kind}] {issue.message}"
