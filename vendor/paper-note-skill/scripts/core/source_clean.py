from __future__ import annotations

import re
from pathlib import Path

COMMENT_LINE_RE = re.compile(r"^\s*%(?!\s*![Tt][Ee][Xx]\b).*$", re.M)
BEGIN_ENV_RE = re.compile(r"\\begin\{([^}]+)\}")
END_ENV_RE = re.compile(r"\\end\{([^}]+)\}")
PROTECTED_ENVIRONMENTS = {
    "verbatim",
    "Verbatim",
    "BVerbatim",
    "lstlisting",
    "minted",
    "filecontents",
    "filecontents*",
}
MATH_ENVIRONMENTS = {
    "align",
    "align*",
    "aligned",
    "alignedat",
    "alignedat*",
    "equation",
    "equation*",
    "gather",
    "gather*",
    "gathered",
    "multline",
    "multline*",
    "split",
    "flalign",
    "flalign*",
}


def update_env_stack(line: str, stack: list[str], tracked_envs: set[str]) -> None:
    for env in BEGIN_ENV_RE.findall(line):
        if env in tracked_envs:
            stack.append(env)
    for env in END_ENV_RE.findall(line):
        if stack and stack[-1] == env:
            stack.pop()
        elif env in stack:
            stack.remove(env)


def preprocess_latex_text(text: str) -> tuple[str, int, int]:
    lines = text.splitlines()
    output: list[str] = []
    protected_stack: list[str] = []
    math_stack: list[str] = []
    pending_blank = False
    removed_comment_lines = 0
    collapsed_blank_lines = 0

    for line in lines:
        if protected_stack:
            output.append(line)
            update_env_stack(line, protected_stack, PROTECTED_ENVIRONMENTS)
            continue

        if COMMENT_LINE_RE.match(line):
            removed_comment_lines += 1
            continue

        if line.strip() == "":
            if math_stack:
                collapsed_blank_lines += 1
                continue
            if output:
                if pending_blank:
                    collapsed_blank_lines += 1
                pending_blank = True
            continue

        if pending_blank:
            output.append("")
            pending_blank = False

        output.append(line)
        update_env_stack(line, protected_stack, PROTECTED_ENVIRONMENTS)
        update_env_stack(line, math_stack, MATH_ENVIRONMENTS)

    return "\n".join(output) + "\n", removed_comment_lines, collapsed_blank_lines


def preprocess_latex_sources(root: Path) -> tuple[int, int, int]:
    changed_files = 0
    removed_comment_lines = 0
    collapsed_blank_lines = 0
    for tex_path in root.rglob("*.tex"):
        original = tex_path.read_text(encoding="utf-8", errors="ignore")
        cleaned, removed_count, collapsed_count = preprocess_latex_text(original)
        if cleaned != original:
            tex_path.write_text(cleaned, encoding="utf-8")
            changed_files += 1
        removed_comment_lines += removed_count
        collapsed_blank_lines += collapsed_count
    return changed_files, removed_comment_lines, collapsed_blank_lines
