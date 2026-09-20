from __future__ import annotations

import re
from dataclasses import dataclass

MATH_MACRO_NAMES = {
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "varepsilon",
    "zeta",
    "eta",
    "theta",
    "vartheta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "pi",
    "varpi",
    "rho",
    "varrho",
    "sigma",
    "varsigma",
    "tau",
    "upsilon",
    "phi",
    "varphi",
    "chi",
    "psi",
    "omega",
    "Gamma",
    "Delta",
    "Theta",
    "Lambda",
    "Xi",
    "Pi",
    "Sigma",
    "Upsilon",
    "Phi",
    "Psi",
    "Omega",
    "bm",
    "boldsymbol",
    "mathbb",
    "mathbf",
    "mathcal",
    "mathrm",
    "mathit",
    "mathsf",
    "mathtt",
    "operatorname",
    "frac",
    "dfrac",
    "tfrac",
    "sqrt",
    "sum",
    "prod",
    "int",
    "oint",
    "lim",
    "min",
    "max",
    "argmin",
    "argmax",
    "exp",
    "log",
    "ln",
    "sin",
    "cos",
    "tan",
    "left",
    "right",
    "cdot",
    "times",
    "otimes",
    "oplus",
    "leq",
    "geq",
    "neq",
    "approx",
    "infty",
    "partial",
    "nabla",
    "forall",
    "exists",
    "in",
    "notin",
}


@dataclass(frozen=True)
class CommandCall:
    name: str
    line: int
    args: tuple[str, ...]


def line_number_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def strip_comments(text: str) -> str:
    stripped_lines: list[str] = []
    for raw_line in text.splitlines(keepends=True):
        line: list[str] = []
        index = 0
        while index < len(raw_line):
            char = raw_line[index]
            if char == "%" and (index == 0 or raw_line[index - 1] != "\\"):
                if raw_line.endswith("\n"):
                    line.append("\n")
                break
            line.append(char)
            index += 1
        stripped_lines.append("".join(line))
    return "".join(stripped_lines)


def parse_braced_group(text: str, start: int) -> tuple[str, int] | None:
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "{":
        return None

    depth = 0
    group_start = index + 1
    cursor = index
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[group_start:cursor], cursor + 1
        cursor += 1
    return None


def parse_command_calls(
    text: str,
    command_name: str,
    min_arg_count: int,
    max_arg_count: int,
) -> list[CommandCall]:
    pattern = re.compile(rf"\\{re.escape(command_name)}(?=\s*\{{)")
    calls: list[CommandCall] = []
    for match in pattern.finditer(text):
        args: list[str] = []
        cursor = match.end()
        for _ in range(max_arg_count):
            parsed = parse_braced_group(text, cursor)
            if parsed is None:
                break
            value, cursor = parsed
            args.append(value)
        if min_arg_count <= len(args) <= max_arg_count:
            calls.append(
                CommandCall(
                    name=command_name,
                    line=line_number_at(text, match.start()),
                    args=tuple(args),
                )
            )
    return calls


def find_annsummary_ranges(text: str) -> tuple[list[tuple[int, int, int]], list[int]]:
    token_re = re.compile(r"\\begin\{annsummary\}|\\end\{annsummary\}")
    stack: list[tuple[int, int]] = []
    ranges: list[tuple[int, int, int]] = []
    unmatched_begin_lines: list[int] = []
    for match in token_re.finditer(text):
        token = match.group(0)
        line = line_number_at(text, match.start())
        if token.startswith(r"\begin"):
            stack.append((match.end(), line))
            continue
        if stack:
            body_start, begin_line = stack.pop()
            ranges.append((body_start, match.start(), begin_line))
        else:
            unmatched_begin_lines.append(line)
    for _, begin_line in stack:
        unmatched_begin_lines.append(begin_line)
    return ranges, unmatched_begin_lines


def find_unmatched_dollars(text: str) -> list[int]:
    stack: list[tuple[str, int]] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "$":
            if index + 1 < len(text) and text[index + 1] == "$":
                kind = "$$"
                if stack and stack[-1][0] == kind:
                    stack.pop()
                else:
                    stack.append((kind, line_number_at(text, index)))
                index += 2
                continue
            kind = "$"
            if stack and stack[-1][0] == kind:
                stack.pop()
            else:
                stack.append((kind, line_number_at(text, index)))
        index += 1
    return [line for _, line in stack]


def find_bare_math_macros(segment: str, base_line: int) -> list[tuple[int, str]]:
    issues: list[tuple[int, str]] = []
    math_stack: list[str] = []
    index = 0
    while index < len(segment):
        char = segment[index]
        if char == "\\":
            if index + 1 >= len(segment):
                break
            next_char = segment[index + 1]
            if next_char.isalpha():
                cursor = index + 1
                while cursor < len(segment) and segment[cursor].isalpha():
                    cursor += 1
                command_name = segment[index + 1 : cursor]
                if not math_stack and command_name in MATH_MACRO_NAMES:
                    line = base_line + segment.count("\n", 0, index)
                    issues.append((line, command_name))
                index = cursor
                continue
            index += 2
            continue
        if char == "$":
            if index + 1 < len(segment) and segment[index + 1] == "$":
                if math_stack and math_stack[-1] == "$$":
                    math_stack.pop()
                else:
                    math_stack.append("$$")
                index += 2
                continue
            if math_stack and math_stack[-1] == "$":
                math_stack.pop()
            else:
                math_stack.append("$")
        index += 1
    return issues


def contains_non_ascii(text: str) -> bool:
    return any(ord(char) > 127 for char in text)


def strip_tex_commands(text: str) -> str:
    return re.sub(r"\\[A-Za-z@]+|\\.", "", text)


def parse_first_optional_arg(text: str, start: int) -> tuple[str, int] | None:
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "[":
        return None

    depth = 0
    group_start = index + 1
    cursor = index
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[group_start:cursor], cursor + 1
        cursor += 1
    return None
