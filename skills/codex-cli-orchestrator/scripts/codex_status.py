#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def tail_text(path: Path, line_count: int) -> list[str]:
    if line_count <= 0 or not path.exists():
        return []
    lines = read_text(path).splitlines()
    return lines[-line_count:]


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def parse_exit_code(path: Path) -> int | None:
    if not path.exists():
        return None
    raw = read_text(path).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_pid(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def pid_is_running(pid: int | None) -> bool | None:
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def mtime_iso(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    delta = datetime.now().astimezone().timestamp() - path.stat().st_mtime
    return round(max(0.0, delta), 1)


def status_reason(summary: dict[str, Any]) -> str:
    if summary.get("next_retry_pending"):
        return "retry_pending"
    if summary["turn_completed"] and summary["exit_code"] in (None, 0):
        return "turn_completed"
    if summary["turn_failed"]:
        return "turn_failed"
    if summary["exit_code"] not in (None, 0):
        return f"exit_code={summary['exit_code']}"
    if summary["event_count"] > 0:
        return "events_present"
    if summary["pid_running"] is True:
        return "pid_running_no_events"
    return "no_events"


def summarize_run(run_dir: Path, stderr_tail_lines: int, text_limit: int) -> dict[str, Any]:
    events_path = run_dir / "events.jsonl"
    stderr_path = run_dir / "stderr.log"
    final_path = run_dir / "final.txt"
    exit_code_path = run_dir / "exit_code.txt"
    pid_path = run_dir / "pid.txt"
    attempt_state = read_json_if_exists(run_dir / "attempt-state.json")
    attempt_history_path = run_dir / "attempt-history.jsonl"

    pid_text = read_text(pid_path).strip() if pid_path.exists() else ""
    pid_value = parse_pid(pid_text)

    summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "updated_at": now_iso(),
        "status": "pending",
        "thread_id": "",
        "event_count": 0,
        "invalid_event_count": 0,
        "item_type_counts": {},
        "command_count": 0,
        "command_completed_count": 0,
        "agent_message_count": 0,
        "last_event_type": "",
        "last_command": "",
        "last_command_status": "",
        "last_command_exit_code": None,
        "last_agent_message": "",
        "final_message": "",
        "final_message_present": final_path.exists() and final_path.stat().st_size > 0,
        "usage": {},
        "turn_completed": False,
        "turn_failed": False,
        "exit_code": parse_exit_code(exit_code_path),
        "pid": pid_text,
        "pid_running": pid_is_running(pid_value),
        "events_mtime": mtime_iso(events_path),
        "events_age_seconds": age_seconds(events_path),
        "stderr_mtime": mtime_iso(stderr_path),
        "stderr_age_seconds": age_seconds(stderr_path),
        "final_mtime": mtime_iso(final_path),
        "final_age_seconds": age_seconds(final_path),
        "stderr_tail": tail_text(stderr_path, stderr_tail_lines),
        "attempt": int(attempt_state.get("current_attempt") or 0),
        "max_attempts": int(attempt_state.get("max_attempts") or 1),
        "retry_on_timeout_max": int(attempt_state.get("retry_on_timeout_max") or 0),
        "retry_count": int(attempt_state.get("retry_count") or 0),
        "timed_out_attempts": int(attempt_state.get("timed_out_attempts") or 0),
        "next_retry_pending": bool(attempt_state.get("next_retry_pending", False)),
        "last_timed_out": bool(attempt_state.get("last_timed_out", False)),
        "attempt_history_count": len(read_text(attempt_history_path).splitlines()) if attempt_history_path.exists() else 0,
        "archived_attempt_count": len(attempt_state.get("archived_attempt_dirs") or []),
    }

    item_counter: Counter[str] = Counter()

    if events_path.exists():
        for raw_line in events_path.open("r", encoding="utf-8", errors="replace"):
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                summary["invalid_event_count"] += 1
                continue

            summary["event_count"] += 1
            event_type = str(event.get("type", ""))
            summary["last_event_type"] = event_type

            if event_type == "thread.started":
                summary["thread_id"] = str(event.get("thread_id", ""))
            elif event_type == "turn.completed":
                summary["turn_completed"] = True
                usage = event.get("usage", {})
                if isinstance(usage, dict):
                    summary["usage"] = usage
            elif event_type == "turn.failed":
                summary["turn_failed"] = True

            item = event.get("item")
            if isinstance(item, dict):
                item_type = str(item.get("type", ""))
                if item_type:
                    item_counter[item_type] += 1

                if item_type == "command_execution":
                    summary["command_count"] += 1 if event_type == "item.started" else 0
                    if event_type == "item.completed":
                        summary["command_completed_count"] += 1
                    summary["last_command"] = truncate(str(item.get("command", "")), text_limit)
                    summary["last_command_status"] = str(item.get("status", ""))
                    summary["last_command_exit_code"] = item.get("exit_code")
                elif item_type == "agent_message" and event_type == "item.completed":
                    summary["agent_message_count"] += 1
                    summary["last_agent_message"] = truncate(str(item.get("text", "")), text_limit)
                elif item_type == "error":
                    summary["turn_failed"] = True

    if final_path.exists():
        summary["final_message"] = truncate(read_text(final_path), text_limit)

    summary["item_type_counts"] = dict(item_counter)

    if summary.get("next_retry_pending"):
        summary["status"] = "pending"
    elif summary["turn_completed"] and summary["exit_code"] in (None, 0):
        summary["status"] = "completed"
    elif summary["turn_failed"] or (summary["exit_code"] not in (None, 0)):
        summary["status"] = "failed"
    elif summary["event_count"] > 0 or summary["pid_running"] is True:
        summary["status"] = "running"
    summary["status_reason"] = status_reason(summary)

    return summary


def summarize_batch(batch_root: Path, stderr_tail_lines: int, text_limit: int) -> dict[str, Any]:
    runs_root = batch_root / "runs"
    runs: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    if runs_root.exists():
        for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
            run_summary = summarize_run(run_dir, stderr_tail_lines, text_limit)
            runs.append(run_summary)
            counts[run_summary["status"]] += 1

    all_done = bool(runs) and all(run["status"] in {"completed", "failed"} for run in runs)

    return {
        "batch_root": str(batch_root),
        "updated_at": now_iso(),
        "run_count": len(runs),
        "status_counts": dict(counts),
        "all_done": all_done,
        "runs": runs,
    }


def format_run_text(payload: dict[str, Any]) -> str:
    lines = [
        f"run: {payload['run_dir']}",
        f"status: {payload['status']} ({payload.get('status_reason', '')})",
        f"pid: {payload.get('pid', '') or '-'} running={payload.get('pid_running', None)}",
        f"thread: {payload.get('thread_id', '') or '-'}",
        f"events: {payload.get('event_count', 0)} invalid={payload.get('invalid_event_count', 0)} age={payload.get('events_age_seconds', None)}s",
        f"attempts: {payload.get('attempt', 0)}/{payload.get('max_attempts', 1)} retries={payload.get('retry_count', 0)}/{payload.get('retry_on_timeout_max', 0)} timed_out={payload.get('timed_out_attempts', 0)} retry_pending={payload.get('next_retry_pending', False)}",
        f"commands: {payload.get('command_completed_count', 0)}/{payload.get('command_count', 0)}",
        f"last command: {payload.get('last_command', '') or '-'}",
        f"last command status: {payload.get('last_command_status', '') or '-'} exit={payload.get('last_command_exit_code', None)}",
        f"last agent: {payload.get('last_agent_message', '') or '-'}",
    ]
    if payload.get("final_message_present"):
        lines.append(f"final: {payload.get('final_message', '') or '-'}")
    if payload.get("stderr_tail"):
        lines.append("stderr tail:")
        lines.extend(f"  {line}" for line in payload["stderr_tail"])
    return "\n".join(lines) + "\n"


def format_batch_text(payload: dict[str, Any]) -> str:
    lines = [
        f"batch: {payload['batch_root']}",
        f"updated: {payload['updated_at']}",
        f"runs: {payload['run_count']} all_done={payload['all_done']} counts={payload['status_counts']}",
    ]
    for run in payload.get("runs", []):
        run_name = Path(run["run_dir"]).name
        lines.append(
            f"- {run_name}: {run['status']} ({run.get('status_reason', '')}) pid={run.get('pid', '') or '-'} "
            f"running={run.get('pid_running', None)} attempt={run.get('attempt', 0)}/{run.get('max_attempts', 1)} "
            f"retries={run.get('retry_count', 0)}/{run.get('retry_on_timeout_max', 0)} "
            f"commands={run.get('command_completed_count', 0)}/{run.get('command_count', 0)}"
        )
        if run.get("last_command"):
            lines.append(f"  last command: {run['last_command']}")
        if run.get("last_agent_message"):
            lines.append(f"  last agent: {run['last_agent_message']}")
    return "\n".join(lines) + "\n"


def resolve_events_path(source: Path) -> Path:
    resolved = source.resolve()
    if resolved.is_dir():
        return resolved / "events.jsonl"
    return resolved


def split_csv_like(values: list[str] | None) -> set[str]:
    if not values:
        return set()
    parts: set[str] = set()
    for value in values:
        for part in value.replace(":", ",").split(","):
            part = part.strip()
            if part:
                parts.add(part)
    return parts


def truncate_line_list(lines: list[str], limit: int) -> list[str]:
    return [truncate(line, limit) for line in lines]


def summarize_event_entry(
    index: int,
    event: dict[str, Any],
    *,
    text_limit: int,
    show_output: bool,
    output_lines: int,
) -> dict[str, Any]:
    event_type = str(event.get("type", ""))
    entry: dict[str, Any] = {
        "index": index,
        "type": event_type,
        "thread_id": str(event.get("thread_id", "")),
        "summary": "",
    }

    if event_type == "thread.started":
        entry["summary"] = f"thread started {entry['thread_id'] or '-'}"
        return entry
    if event_type == "turn.started":
        entry["summary"] = "turn started"
        return entry
    if event_type == "turn.completed":
        usage = event.get("usage", {})
        if isinstance(usage, dict) and usage:
            usage_summary = ", ".join(f"{key}={value}" for key, value in usage.items())
            entry["usage"] = usage
            entry["summary"] = f"turn completed ({usage_summary})"
        else:
            entry["summary"] = "turn completed"
        return entry
    if event_type == "turn.failed":
        entry["summary"] = "turn failed"
        return entry

    item = event.get("item")
    if not isinstance(item, dict):
        entry["summary"] = truncate(json.dumps(event, ensure_ascii=False), text_limit)
        return entry

    item_type = str(item.get("type", ""))
    item_id = str(item.get("id", ""))
    status = str(item.get("status", ""))
    entry["item_id"] = item_id
    entry["item_type"] = item_type
    if status:
        entry["status"] = status
    if item_type == "command_execution":
        command = str(item.get("command", ""))
        output = str(item.get("aggregated_output", ""))
        output_lines_all = output.splitlines()
        entry["command"] = command
        entry["exit_code"] = item.get("exit_code")
        entry["output_line_count"] = len(output_lines_all)
        entry["summary"] = truncate(command, text_limit)
        if show_output and output_lines > 0 and output_lines_all:
            entry["output_preview"] = truncate_line_list(output_lines_all[-output_lines:], text_limit)
        return entry
    if item_type == "agent_message":
        text = str(item.get("text", ""))
        entry["text"] = text
        entry["summary"] = truncate(text, text_limit)
        return entry
    if item_type == "todo_list":
        todo_items = item.get("items") if isinstance(item.get("items"), list) else []
        simplified = []
        done_count = 0
        for todo in todo_items:
            if not isinstance(todo, dict):
                continue
            completed = bool(todo.get("completed"))
            if completed:
                done_count += 1
            simplified.append({"text": str(todo.get("text", "")), "completed": completed})
        entry["items"] = simplified
        entry["summary"] = f"todo list {done_count}/{len(simplified)} completed"
        return entry
    if item_type == "file_change":
        changes = item.get("changes") if isinstance(item.get("changes"), list) else []
        simplified = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            simplified.append({"path": str(change.get("path", "")), "kind": str(change.get("kind", ""))})
        entry["changes"] = simplified
        if simplified:
            labels = [f"{change['kind']} {change['path']}" for change in simplified]
            entry["summary"] = truncate("; ".join(labels), text_limit)
        else:
            entry["summary"] = "file change"
        return entry
    if item_type == "error":
        text = truncate(json.dumps(item, ensure_ascii=False), text_limit)
        entry["summary"] = text
        return entry

    entry["summary"] = truncate(json.dumps(item, ensure_ascii=False), text_limit)
    return entry


def summarize_events(
    source: Path,
    *,
    tail: int,
    item_types: set[str],
    event_types: set[str],
    include_started: bool,
    text_limit: int,
    show_output: bool,
    output_lines: int,
) -> dict[str, Any]:
    events_path = resolve_events_path(source)
    if not events_path.exists():
        raise FileNotFoundError(f"missing events file: {events_path}")

    raw_entries: list[dict[str, Any]] = []
    invalid_event_count = 0
    total_event_count = 0

    with events_path.open("r", encoding="utf-8", errors="replace") as handle:
        for index, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            total_event_count += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                invalid_event_count += 1
                continue

            event_type = str(event.get("type", ""))
            if not include_started and event_type == "item.started":
                continue
            if event_types and event_type not in event_types:
                continue

            item = event.get("item")
            item_type = str(item.get("type", "")) if isinstance(item, dict) else ""
            if item_types and item_type not in item_types:
                continue

            raw_entries.append(
                summarize_event_entry(
                    index,
                    event,
                    text_limit=text_limit,
                    show_output=show_output,
                    output_lines=output_lines,
                )
            )

    selected_entries = raw_entries[-tail:] if tail > 0 else raw_entries
    run_dir = events_path.parent if events_path.name == "events.jsonl" else Path("")
    return {
        "events_path": str(events_path),
        "run_dir": str(run_dir) if run_dir else "",
        "updated_at": now_iso(),
        "total_event_count": total_event_count,
        "selected_event_count": len(selected_entries),
        "invalid_event_count": invalid_event_count,
        "tail": tail,
        "filters": {
            "item_types": sorted(item_types),
            "event_types": sorted(event_types),
            "include_started": include_started,
            "show_output": show_output,
            "output_lines": output_lines,
        },
        "events": selected_entries,
    }


def format_events_text(payload: dict[str, Any]) -> str:
    lines = [
        f"events: {payload['events_path']}",
        f"updated: {payload['updated_at']}",
        f"selected: {payload['selected_event_count']}/{payload['total_event_count']} invalid={payload['invalid_event_count']}",
    ]
    filters = payload.get("filters", {})
    if filters:
        lines.append(
            "filters: "
            f"item_types={filters.get('item_types', []) or '-'} "
            f"event_types={filters.get('event_types', []) or '-'} "
            f"include_started={filters.get('include_started', False)} "
            f"show_output={filters.get('show_output', False)}"
        )

    for entry in payload.get("events", []):
        parts = [f"[{entry['index']:04d}]", entry.get("type", "")]
        if entry.get("item_type"):
            parts.append(entry["item_type"])
        if entry.get("item_id"):
            parts.append(entry["item_id"])
        if entry.get("status"):
            parts.append(f"status={entry['status']}")
        if entry.get("exit_code") is not None:
            parts.append(f"exit={entry['exit_code']}")
        lines.append(" ".join(parts))
        if entry.get("summary"):
            lines.append(f"  {entry['summary']}")
        if entry.get("items"):
            for todo in entry["items"]:
                marker = "x" if todo.get("completed") else " "
                lines.append(f"  [{marker}] {todo.get('text', '')}")
        if entry.get("changes"):
            for change in entry["changes"]:
                lines.append(f"  {change.get('kind', '')}: {change.get('path', '')}")
        if entry.get("output_line_count") and not filters.get("show_output", False):
            lines.append(f"  output: {entry['output_line_count']} lines")
        for preview_line in entry.get("output_preview", []):
            lines.append(f"  | {preview_line}")

    return "\n".join(lines) + "\n"


def write_output(payload: dict[str, Any], output_path: Path | None, output_format: str, command: str) -> None:
    if output_format == "text":
        if command == "single":
            text = format_run_text(payload)
        elif command == "batch":
            text = format_batch_text(payload)
        else:
            text = format_events_text(payload)
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize codex exec run or batch status from files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    single = subparsers.add_parser("single", help="Summarize one run directory.")
    single.add_argument("run_dir", type=Path)
    single.add_argument("--write", type=Path)
    single.add_argument("--stderr-tail-lines", type=int, default=20)
    single.add_argument("--text-limit", type=int, default=240)
    single.add_argument("--format", choices=("json", "text"), default="json")

    batch = subparsers.add_parser("batch", help="Summarize one batch root.")
    batch.add_argument("batch_root", type=Path)
    batch.add_argument("--write", type=Path)
    batch.add_argument("--stderr-tail-lines", type=int, default=12)
    batch.add_argument("--text-limit", type=int, default=200)
    batch.add_argument("--format", choices=("json", "text"), default="json")

    events = subparsers.add_parser("events", help="Render one events.jsonl file or run directory as a readable timeline.")
    events.add_argument("source", type=Path, help="Run directory or events.jsonl path.")
    events.add_argument("--write", type=Path)
    events.add_argument("--tail", type=int, default=60, help="Last N matching events; 0 means all.")
    events.add_argument("--item-type", action="append", help="Filter by item type. Repeat or pass comma-separated values.")
    events.add_argument("--event-type", action="append", help="Filter by event type. Repeat or pass comma-separated values.")
    events.add_argument("--include-started", action="store_true", help="Include item.started events; default focuses on completed items.")
    events.add_argument("--show-output", action="store_true", help="Include truncated command output previews.")
    events.add_argument("--output-lines", type=int, default=4, help="Number of output lines to show when --show-output is set.")
    events.add_argument("--text-limit", type=int, default=220)
    events.add_argument("--format", choices=("json", "text"), default="text")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "single":
        payload = summarize_run(args.run_dir.resolve(), args.stderr_tail_lines, args.text_limit)
        write_output(payload, args.write, args.format, args.command)
        return 0

    if args.command == "events":
        payload = summarize_events(
            args.source,
            tail=args.tail,
            item_types=split_csv_like(args.item_type),
            event_types=split_csv_like(args.event_type),
            include_started=args.include_started,
            text_limit=args.text_limit,
            show_output=args.show_output,
            output_lines=args.output_lines,
        )
        write_output(payload, args.write, args.format, args.command)
        return 0

    payload = summarize_batch(args.batch_root.resolve(), args.stderr_tail_lines, args.text_limit)
    write_output(payload, args.write, args.format, args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
