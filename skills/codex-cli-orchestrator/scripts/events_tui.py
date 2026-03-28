#!/usr/bin/env python3
from __future__ import annotations

import argparse
import curses
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_status import resolve_events_path, split_csv_like


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

FG_RED = "\033[31m"
FG_GREEN = "\033[32m"
FG_YELLOW = "\033[33m"
FG_BLUE = "\033[34m"
FG_MAGENTA = "\033[35m"
FG_CYAN = "\033[36m"
FG_WHITE = "\033[37m"
FG_BRIGHT_BLACK = "\033[90m"

MAX_OUTPUT_CAPTURE_LINES = 160


@dataclass
class TodoItem:
    completed: bool
    text: str


@dataclass
class FileChange:
    kind: str
    path: str


@dataclass
class EventRecord:
    index: int
    event_type: str
    item_type: str = ""
    item_id: str = ""
    status: str = ""
    exit_code: int | None = None
    summary: str = ""
    thread_id: str = ""
    usage_summary: str = ""
    command: str = ""
    text: str = ""
    todo_items: list[TodoItem] = field(default_factory=list)
    changes: list[FileChange] = field(default_factory=list)
    output_line_count: int = 0
    output_text: str = ""
    raw_json: str = ""


@dataclass
class EventDataset:
    events_path: Path
    total_event_count: int
    invalid_event_count: int
    records: list[EventRecord]
    mtime_ns: int = 0
    size: int = 0


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def flatten(text: str, limit: int) -> str:
    return truncate(" ".join(text.split()), limit)


def supports_ansi(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty() and os.environ.get("TERM", "") not in {"", "dumb"}


def ansi(text: str, *codes: str, enabled: bool) -> str:
    if not enabled or not codes:
        return text
    return "".join(codes) + text + RESET


def event_color_name(record: EventRecord) -> str:
    if record.event_type.startswith("turn.") or record.event_type.startswith("thread."):
        return "cyan"
    if record.item_type == "command_execution":
        return "blue"
    if record.item_type == "agent_message":
        return "cyan"
    if record.item_type == "todo_list":
        return "magenta"
    if record.item_type == "file_change":
        return "yellow"
    if record.item_type == "error":
        return "red"
    return "white"


def status_color_name(status: str, exit_code: int | None) -> str:
    if exit_code is not None:
        return "green" if exit_code == 0 else "red"
    if status in {"completed", "ok", "success"}:
        return "green"
    if status in {"in_progress", "running", "started"}:
        return "yellow"
    if status in {"failed", "error"}:
        return "red"
    return "white"


def record_matches(
    event_type: str,
    item_type: str,
    *,
    event_types: set[str],
    item_types: set[str],
    include_started: bool,
) -> bool:
    if not include_started and event_type == "item.started":
        return False
    if event_types and event_type not in event_types:
        return False
    if item_types and item_type not in item_types:
        return False
    return True


def parse_output_tail(text: str, capture_lines: int) -> tuple[int, list[str]]:
    if not text:
        return 0, []
    lines = text.splitlines()
    return len(lines), lines[-capture_lines:]


def parse_record(index: int, event: dict[str, Any], *, text_limit: int) -> EventRecord:
    event_type = str(event.get("type", ""))
    record = EventRecord(index=index, event_type=event_type)
    record.raw_json = json.dumps(event, ensure_ascii=False, indent=2)

    if event_type == "thread.started":
        record.thread_id = str(event.get("thread_id", ""))
        record.summary = f"thread started {record.thread_id or '-'}"
        return record
    if event_type == "turn.started":
        record.summary = "turn started"
        return record
    if event_type == "turn.completed":
        usage = event.get("usage", {})
        if isinstance(usage, dict) and usage:
            record.usage_summary = ", ".join(f"{key}={value}" for key, value in usage.items())
            record.summary = f"turn completed ({record.usage_summary})"
        else:
            record.summary = "turn completed"
        return record
    if event_type == "turn.failed":
        record.summary = "turn failed"
        return record

    item = event.get("item")
    if not isinstance(item, dict):
        record.summary = truncate(json.dumps(event, ensure_ascii=False), text_limit)
        return record

    record.item_type = str(item.get("type", ""))
    record.item_id = str(item.get("id", ""))
    record.status = str(item.get("status", ""))
    exit_code = item.get("exit_code")
    if isinstance(exit_code, int):
        record.exit_code = exit_code

    if record.item_type == "command_execution":
        record.command = str(item.get("command", ""))
        record.summary = flatten(record.command, text_limit)
        record.output_text = str(item.get("aggregated_output", ""))
        output_count, _output_tail = parse_output_tail(record.output_text, MAX_OUTPUT_CAPTURE_LINES)
        record.output_line_count = output_count
        return record

    if record.item_type == "agent_message":
        record.text = str(item.get("text", ""))
        record.summary = flatten(record.text, text_limit)
        return record

    if record.item_type == "todo_list":
        done_count = 0
        items = item.get("items") if isinstance(item.get("items"), list) else []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            completed = bool(raw.get("completed"))
            if completed:
                done_count += 1
            record.todo_items.append(TodoItem(completed=completed, text=str(raw.get("text", ""))))
        record.summary = f"todo list {done_count}/{len(record.todo_items)} completed"
        return record

    if record.item_type == "file_change":
        changes = item.get("changes") if isinstance(item.get("changes"), list) else []
        labels: list[str] = []
        for raw in changes:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind", ""))
            path = str(raw.get("path", ""))
            record.changes.append(FileChange(kind=kind, path=path))
            labels.append(f"{kind} {path}".strip())
        record.summary = truncate("; ".join(labels) if labels else "file change", text_limit)
        return record

    if record.item_type == "error":
        record.summary = truncate(json.dumps(item, ensure_ascii=False), text_limit)
        return record

    record.summary = truncate(json.dumps(item, ensure_ascii=False), text_limit)
    return record


def load_dataset(
    events_path: Path,
    *,
    tail: int,
    item_types: set[str],
    event_types: set[str],
    include_started: bool,
    text_limit: int,
) -> EventDataset:
    if not events_path.exists():
        return EventDataset(events_path=events_path, total_event_count=0, invalid_event_count=0, records=[])

    total_event_count = 0
    invalid_event_count = 0
    records: list[EventRecord] = []

    with events_path.open("r", encoding="utf-8", errors="replace") as handle:
        for index, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            total_event_count += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if not raw_line.endswith("\n"):
                    break
                invalid_event_count += 1
                continue

            item = event.get("item")
            item_type = str(item.get("type", "")) if isinstance(item, dict) else ""
            event_type = str(event.get("type", ""))
            if not record_matches(
                event_type,
                item_type,
                event_types=event_types,
                item_types=item_types,
                include_started=include_started,
            ):
                continue

            records.append(parse_record(index, event, text_limit=text_limit))

    if tail > 0:
        records = records[-tail:]

    stat = events_path.stat()
    return EventDataset(
        events_path=events_path,
        total_event_count=total_event_count,
        invalid_event_count=invalid_event_count,
        records=records,
        mtime_ns=stat.st_mtime_ns,
        size=stat.st_size,
    )


def wrap_text_block(label: str, text: str, width: int) -> list[str]:
    prefix = f"{label}: "
    available = max(12, width - len(prefix) - 1)
    lines: list[str] = []
    first = True
    raw_lines = text.splitlines() or [""]
    for raw in raw_lines:
        chunks = textwrap.wrap(
            raw,
            width=available,
            break_long_words=False,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=False,
        )
        if not chunks:
            chunks = [""]
        for chunk in chunks:
            if first:
                lines.append(prefix + chunk)
                first = False
            else:
                lines.append(" " * len(prefix) + chunk)
    return lines


def format_list_line(record: EventRecord, width: int) -> str:
    parts = [f"{record.index:04d}", f"[{record.event_type}]"]
    if record.item_type:
        parts.append(f"[{record.item_type}]")
    if record.status:
        parts.append(f"[{record.status}]")
    if record.exit_code is not None:
        parts.append(f"[exit {record.exit_code}]")
    if record.summary:
        parts.append(record.summary)
    return truncate(" ".join(parts), max(20, width - 1))


def format_detail_header(record: EventRecord) -> str:
    parts = [f"{record.index:04d}", f"[{record.event_type}]"]
    if record.item_type:
        parts.append(f"[{record.item_type}]")
    if record.status:
        parts.append(f"[{record.status}]")
    if record.exit_code is not None:
        parts.append(f"[exit {record.exit_code}]")
    if record.item_id:
        parts.append(record.item_id)
    return " ".join(parts)


def build_detail_lines(record: EventRecord, width: int, *, show_output: bool, output_lines: int) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    header = format_detail_header(record)
    lines.append((header, event_color_name(record)))

    if record.thread_id:
        for line in wrap_text_block("thread", record.thread_id, width):
            lines.append((line, "cyan"))
    if record.usage_summary:
        for line in wrap_text_block("usage", record.usage_summary, width):
            lines.append((line, "cyan"))
    if record.command:
        for line in wrap_text_block("cmd", record.command, width):
            lines.append((line, "blue"))
    if record.text:
        for line in wrap_text_block("msg", record.text, width):
            lines.append((line, "cyan"))
    if record.todo_items:
        lines.append((f"todo: {record.summary}", "magenta"))
        for item in record.todo_items:
            marker = "[x]" if item.completed else "[ ]"
            label = f"{marker} {item.text}"
            for idx, line in enumerate(wrap_text_block("", label, width)):
                if idx == 0:
                    lines.append(("  " + line.lstrip(), "green" if item.completed else "yellow"))
                else:
                    lines.append(("  " + line.lstrip(), "green" if item.completed else "yellow"))
    if record.changes:
        lines.append((f"file: {record.summary}", "yellow"))
        for change in record.changes:
            for line in wrap_text_block(change.kind or "change", change.path, width):
                lines.append((line, "yellow"))
    if record.output_line_count:
        if show_output and record.output_text:
            shown = record.output_text.splitlines()
            lines.append((f"out: showing full output ({len(shown)} lines)", "magenta"))
            for raw in shown:
                for line in wrap_text_block("|", raw, width):
                    lines.append((line, "magenta"))
        else:
            lines.append((f"out: hidden ({record.output_line_count} lines), press o to toggle full output", "dim"))
    if len(lines) == 1 and record.raw_json:
        lines.append(("json: full event payload", "dim"))
        for line in wrap_text_block("json", record.raw_json, width):
            lines.append((line, "dim"))
    elif len(lines) == 1:
        lines.append(("info: no additional details", "dim"))
    return lines


def render_text_snapshot(
    dataset: EventDataset,
    *,
    width: int,
    show_output: bool,
    output_lines: int,
    color_mode: str,
    follow: bool,
    include_started: bool,
) -> str:
    enabled = supports_ansi(color_mode)
    lines = [
        ansi("Codex Events TUI", BOLD, FG_WHITE, enabled=enabled),
        ansi(str(dataset.events_path), FG_CYAN, enabled=enabled),
        ansi(
            f"selected={len(dataset.records)}/{dataset.total_event_count} invalid={dataset.invalid_event_count} "
            f"follow={'on' if follow else 'off'} include_started={'yes' if include_started else 'no'}",
            DIM,
            FG_BRIGHT_BLACK,
            enabled=enabled,
        ),
        ansi("-" * min(width, 120), FG_BRIGHT_BLACK, enabled=enabled),
    ]
    for record in dataset.records:
        color_name = event_color_name(record)
        color_code = {
            "cyan": FG_CYAN,
            "blue": FG_BLUE,
            "magenta": FG_MAGENTA,
            "yellow": FG_YELLOW,
            "green": FG_GREEN,
            "red": FG_RED,
            "dim": FG_BRIGHT_BLACK,
            "white": FG_WHITE,
        }.get(color_name, FG_WHITE)
        lines.append(ansi(format_list_line(record, width), BOLD, color_code, enabled=enabled))
        for detail, detail_color in build_detail_lines(record, width, show_output=show_output, output_lines=output_lines)[1:]:
            detail_code = {
                "cyan": FG_CYAN,
                "blue": FG_BLUE,
                "magenta": FG_MAGENTA,
                "yellow": FG_YELLOW,
                "green": FG_GREEN,
                "red": FG_RED,
                "dim": FG_BRIGHT_BLACK,
                "white": FG_WHITE,
            }.get(detail_color, FG_WHITE)
            lines.append(ansi(detail, detail_code, enabled=enabled))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def safe_addnstr(window: curses.window, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
    if width <= 0:
        return
    try:
        window.addnstr(y, x, text, width, attr)
    except curses.error:
        pass


def ensure_visible(index: int, offset: int, height: int, total: int) -> int:
    if total <= 0 or height <= 0:
        return 0
    offset = max(0, min(offset, max(0, total - 1)))
    if index < offset:
        return index
    if index >= offset + height:
        return max(0, index - height + 1)
    return offset


def init_palette(color_enabled: bool) -> dict[str, int]:
    palette = {
        "default": curses.A_NORMAL,
        "white": curses.A_BOLD,
        "cyan": curses.A_BOLD,
        "blue": curses.A_BOLD,
        "magenta": curses.A_BOLD,
        "yellow": curses.A_BOLD,
        "green": curses.A_BOLD,
        "red": curses.A_BOLD,
        "dim": curses.A_DIM,
    }
    if not color_enabled or not curses.has_colors():
        return palette

    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_CYAN, -1)
    curses.init_pair(3, curses.COLOR_BLUE, -1)
    curses.init_pair(4, curses.COLOR_MAGENTA, -1)
    curses.init_pair(5, curses.COLOR_YELLOW, -1)
    curses.init_pair(6, curses.COLOR_GREEN, -1)
    curses.init_pair(7, curses.COLOR_RED, -1)

    palette.update(
        {
            "white": curses.color_pair(1) | curses.A_BOLD,
            "cyan": curses.color_pair(2) | curses.A_BOLD,
            "blue": curses.color_pair(3) | curses.A_BOLD,
            "magenta": curses.color_pair(4) | curses.A_BOLD,
            "yellow": curses.color_pair(5) | curses.A_BOLD,
            "green": curses.color_pair(6) | curses.A_BOLD,
            "red": curses.color_pair(7) | curses.A_BOLD,
            "dim": curses.A_DIM,
        }
    )
    return palette


class EventsViewer:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.events_path = resolve_events_path(args.source)
        self.item_types = split_csv_like(args.item_type)
        self.event_types = split_csv_like(args.event_type)
        self.dataset = load_dataset(
            self.events_path,
            tail=args.tail,
            item_types=self.item_types,
            event_types=self.event_types,
            include_started=args.include_started,
            text_limit=args.text_limit,
        )
        self.selected = max(0, len(self.dataset.records) - 1)
        self.list_offset = max(0, len(self.dataset.records) - 1)
        self.detail_offset = 0
        self.detail_open = False
        self.focus = "list"
        self.follow = bool(args.follow)
        self.show_output = bool(args.show_output)
        self.last_poll = 0.0
        self.message = ""

    def selected_record(self) -> EventRecord | None:
        if not self.dataset.records:
            return None
        self.selected = max(0, min(self.selected, len(self.dataset.records) - 1))
        return self.dataset.records[self.selected]

    def reload(self, *, force: bool = False) -> bool:
        old = self.dataset
        try:
            stat = self.events_path.stat()
            current_sig = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            current_sig = (0, 0)

        if not force and current_sig == (old.mtime_ns, old.size):
            return False

        old_selected_index = self.selected_record().index if self.selected_record() else None
        old_at_end = bool(old.records) and self.selected >= len(old.records) - 1

        self.dataset = load_dataset(
            self.events_path,
            tail=self.args.tail,
            item_types=self.item_types,
            event_types=self.event_types,
            include_started=self.args.include_started,
            text_limit=self.args.text_limit,
        )

        if not self.dataset.records:
            self.selected = 0
            self.list_offset = 0
            self.detail_offset = 0
            return True

        if old_selected_index is not None:
            for idx, record in enumerate(self.dataset.records):
                if record.index == old_selected_index:
                    self.selected = idx
                    break
            else:
                self.selected = len(self.dataset.records) - 1 if (self.follow and old_at_end) else min(self.selected, len(self.dataset.records) - 1)
        else:
            self.selected = len(self.dataset.records) - 1 if self.follow else min(self.selected, len(self.dataset.records) - 1)

        if self.follow and old_at_end:
            self.selected = len(self.dataset.records) - 1
        return True

    def move_selection(self, delta: int) -> None:
        if not self.dataset.records:
            return
        self.selected = max(0, min(self.selected + delta, len(self.dataset.records) - 1))
        self.detail_offset = 0

    def move_to_edge(self, end: bool) -> None:
        if not self.dataset.records:
            return
        self.selected = len(self.dataset.records) - 1 if end else 0
        self.detail_offset = 0

    def toggle_detail(self) -> None:
        self.detail_open = not self.detail_open
        if not self.detail_open:
            self.focus = "list"
        self.detail_offset = 0

    def toggle_focus(self) -> None:
        if not self.detail_open:
            return
        self.focus = "detail" if self.focus == "list" else "list"

    def scroll_detail(self, delta: int, pane_height: int, detail_len: int) -> None:
        if pane_height <= 0 or detail_len <= pane_height:
            self.detail_offset = 0
            return
        self.detail_offset = max(0, min(self.detail_offset + delta, detail_len - pane_height))

    def draw(self, stdscr: curses.window) -> None:
        stdscr.erase()
        rows, cols = stdscr.getmaxyx()
        palette = init_palette(self.args.color != "never")

        header_rows = 3
        footer_rows = 1
        detail_rows = max(8, rows // 3) if self.detail_open and rows >= 14 else 0
        separator_rows = 1 if detail_rows else 0
        list_rows = max(1, rows - header_rows - footer_rows - detail_rows - separator_rows)

        selected_record = self.selected_record()
        detail_lines = build_detail_lines(
            selected_record,
            max(20, cols - 2),
            show_output=self.show_output,
            output_lines=self.args.output_lines,
        ) if (selected_record and detail_rows) else []

        self.list_offset = ensure_visible(self.selected, self.list_offset, list_rows, len(self.dataset.records))
        if detail_rows:
            self.scroll_detail(0, detail_rows, len(detail_lines))

        mode_bits = [f"follow={'on' if self.follow else 'off'}", f"focus={self.focus}"]
        if self.detail_open:
            mode_bits.append("detail=open")
        if self.show_output:
            mode_bits.append(f"output={self.args.output_lines}")

        safe_addnstr(stdscr, 0, 0, "Codex Events TUI", cols - 1, palette["white"])
        safe_addnstr(stdscr, 0, max(20, cols - len("  ".join(mode_bits)) - 2), "  ".join(mode_bits), cols - 1, palette["dim"])
        safe_addnstr(stdscr, 1, 0, truncate(str(self.events_path), cols - 1), cols - 1, palette["cyan"])
        filter_line = (
            f"selected={len(self.dataset.records)}/{self.dataset.total_event_count} invalid={self.dataset.invalid_event_count} "
            f"include_started={'yes' if self.args.include_started else 'no'}"
        )
        if self.item_types:
            filter_line += " item_types=" + ",".join(sorted(self.item_types))
        if self.event_types:
            filter_line += " event_types=" + ",".join(sorted(self.event_types))
        safe_addnstr(stdscr, 2, 0, truncate(filter_line, cols - 1), cols - 1, palette["dim"])

        if not self.dataset.records:
            safe_addnstr(stdscr, header_rows, 0, "No matching events yet. Press f to follow, r to reload, q to quit.", cols - 1, palette["dim"])
        else:
            for row in range(list_rows):
                idx = self.list_offset + row
                if idx >= len(self.dataset.records):
                    break
                record = self.dataset.records[idx]
                y = header_rows + row
                line = format_list_line(record, cols - 1)
                attr = palette.get(event_color_name(record), palette["default"])
                if idx == self.selected:
                    attr |= curses.A_REVERSE | curses.A_BOLD
                safe_addnstr(stdscr, y, 0, line, cols - 1, attr)

        if detail_rows:
            sep_y = header_rows + list_rows
            safe_addnstr(stdscr, sep_y, 0, "-" * max(1, cols - 1), cols - 1, palette["dim"])
            detail_start = sep_y + 1
            visible = detail_lines[self.detail_offset : self.detail_offset + detail_rows]
            for row, (line, color_name) in enumerate(visible):
                safe_addnstr(stdscr, detail_start + row, 0, truncate(line, cols - 1), cols - 1, palette.get(color_name, palette["default"]))

        help_text = "q quit  j/k/arrows move  enter expand  tab focus  f follow  o output  r reload  g/G home/end"
        if self.focus == "detail":
            help_text = "detail focus: j/k/arrows scroll  tab back  o output  f follow  q quit"
        safe_addnstr(stdscr, rows - 1, 0, truncate(help_text, cols - 1), cols - 1, palette["dim"])
        stdscr.refresh()

    def run(self, stdscr: curses.window) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        stdscr.keypad(True)
        stdscr.timeout(200)

        while True:
            now = time.monotonic()
            if self.follow and now - self.last_poll >= self.args.poll_interval:
                self.reload(force=False)
                self.last_poll = now

            self.draw(stdscr)
            key = stdscr.getch()
            if key == -1:
                continue
            if key in (ord("q"), ord("Q")):
                return
            if key in (ord("r"), ord("R")):
                self.reload(force=True)
                continue
            if key in (ord("f"), ord("F")):
                self.follow = not self.follow
                if self.follow and self.dataset.records:
                    self.selected = len(self.dataset.records) - 1
                continue
            if key in (ord("o"), ord("O")):
                self.show_output = not self.show_output
                self.detail_offset = 0
                continue
            if key in (9,):
                self.toggle_focus()
                continue
            if key in (10, 13, ord(" ")):
                self.toggle_detail()
                continue

            detail_rows = max(8, stdscr.getmaxyx()[0] // 3) if self.detail_open and stdscr.getmaxyx()[0] >= 14 else 0
            detail_len = 0
            if detail_rows and self.selected_record():
                detail_len = len(build_detail_lines(self.selected_record(), max(20, stdscr.getmaxyx()[1] - 2), show_output=self.show_output, output_lines=self.args.output_lines))

            if self.focus == "detail" and self.detail_open:
                if key in (curses.KEY_UP, ord("k")):
                    self.scroll_detail(-1, detail_rows, detail_len)
                    continue
                if key in (curses.KEY_DOWN, ord("j")):
                    self.scroll_detail(1, detail_rows, detail_len)
                    continue
                if key == curses.KEY_PPAGE:
                    self.scroll_detail(-(detail_rows - 1), detail_rows, detail_len)
                    continue
                if key == curses.KEY_NPAGE:
                    self.scroll_detail(detail_rows - 1, detail_rows, detail_len)
                    continue

            if key in (curses.KEY_UP, ord("k")):
                self.move_selection(-1)
                continue
            if key in (curses.KEY_DOWN, ord("j")):
                self.move_selection(1)
                continue
            if key == curses.KEY_PPAGE:
                self.move_selection(-(max(1, stdscr.getmaxyx()[0] // 4)))
                continue
            if key == curses.KEY_NPAGE:
                self.move_selection(max(1, stdscr.getmaxyx()[0] // 4))
                continue
            if key in (ord("g"), curses.KEY_HOME):
                self.move_to_edge(False)
                continue
            if key in (ord("G"), curses.KEY_END):
                self.move_to_edge(True)
                continue


def write_via_pager(text: str) -> None:
    pager = shutil.which("less")
    if not pager or not sys.stdout.isatty():
        sys.stdout.write(text)
        return
    proc = subprocess.Popen([pager, "-R", "-F", "-X"], stdin=subprocess.PIPE, text=True)
    assert proc.stdin is not None
    try:
        proc.stdin.write(text)
    finally:
        proc.stdin.close()
    proc.wait()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive terminal viewer for Codex events.jsonl files.")
    parser.add_argument("source", type=Path, help="Run directory or events.jsonl path.")
    parser.add_argument("--tail", type=int, default=120, help="Last N matching events; 0 means all.")
    parser.add_argument("--item-type", action="append", help="Filter by item type. Repeat or pass comma-separated values.")
    parser.add_argument("--event-type", action="append", help="Filter by event type. Repeat or pass comma-separated values.")
    parser.add_argument("--include-started", action="store_true", help="Include item.started events.")
    parser.add_argument("--show-output", action="store_true", help="Start with command output previews enabled.")
    parser.add_argument("--output-lines", type=int, default=12, help="Command output tail lines shown in expanded detail.")
    parser.add_argument("--text-limit", type=int, default=1200, help="Truncation limit for one-line summaries.")
    parser.add_argument("--width", type=int, default=0, help="Static render width; 0 uses terminal width.")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--follow", action="store_true", help="Poll the events file and refresh when it grows.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between follow-mode refreshes.")
    parser.add_argument("--mode", choices=("auto", "tui", "text"), default="auto", help="`tui` for curses UI, `text` for static snapshot.")
    parser.add_argument("--write", type=Path, help="Write a static snapshot to a file.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.write is not None:
        dataset = load_dataset(
            resolve_events_path(args.source),
            tail=args.tail,
            item_types=split_csv_like(args.item_type),
            event_types=split_csv_like(args.event_type),
            include_started=args.include_started,
            text_limit=args.text_limit,
        )
        width = args.width or shutil.get_terminal_size((120, 40)).columns
        text = render_text_snapshot(
            dataset,
            width=width,
            show_output=args.show_output,
            output_lines=args.output_lines,
            color_mode="never",
            follow=args.follow,
            include_started=args.include_started,
        )
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text, encoding="utf-8")
        return 0

    use_tui = args.mode == "tui" or (
        args.mode == "auto" and sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM", "") not in {"", "dumb"}
    )

    if use_tui:
        viewer = EventsViewer(args)
        curses.wrapper(viewer.run)
        return 0

    dataset = load_dataset(
        resolve_events_path(args.source),
        tail=args.tail,
        item_types=split_csv_like(args.item_type),
        event_types=split_csv_like(args.event_type),
        include_started=args.include_started,
        text_limit=args.text_limit,
    )
    width = args.width or shutil.get_terminal_size((120, 40)).columns
    text = render_text_snapshot(
        dataset,
        width=width,
        show_output=args.show_output,
        output_lines=args.output_lines,
        color_mode=args.color,
        follow=args.follow,
        include_started=args.include_started,
    )
    write_via_pager(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
