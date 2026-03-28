#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_TRACE_ENV_KEYS = [
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "VIDEO_NOTE_PIPELINE_REPO",
    "VIDEO_NOTE_WORKSPACE_ROOT",
]

ATTEMPT_ARCHIVE_FILES = [
    "command.txt",
    "run-meta.txt",
    "events.jsonl",
    "stderr.log",
    "final.txt",
    "summary.json",
    "exit_code.txt",
    "pid.txt",
    "launcher.stdout.log",
    "launcher.stderr.log",
    "result.txt",
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "job"


def load_jobs(manifest_path: Path) -> list[dict[str, Any]]:
    text = manifest_path.read_text(encoding="utf-8", errors="replace")
    if manifest_path.suffix == ".json":
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("JSON manifest must be a list of job objects")
        jobs = payload
    else:
        jobs = []
        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                jobs.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL line {lineno}: {exc}") from exc
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise ValueError(f"job #{index + 1} is not an object")
    return jobs


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_jsonl(path: Path, payloads: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for payload in payloads:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_nonnegative_int(value: Any, *, default: int, field_name: str) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"{field_name} must be an integer") from exc
    if parsed < 0:
        raise SystemExit(f"{field_name} must be >= 0")
    return parsed


def parse_result_marker(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def marker_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes"}:
        return True
    if lowered in {"0", "false", "no"}:
        return False
    return None


def did_attempt_timeout(job: dict[str, Any], exit_code: int, result_marker: dict[str, str]) -> bool:
    explicit = marker_bool(result_marker.get("timed_out"))
    if explicit is not None:
        return explicit
    return bool(job.get("outer_timeout")) and exit_code in {124, 137}


def initial_attempt_state(job_id: str, retry_on_timeout_max: int) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "retry_on_timeout_max": retry_on_timeout_max,
        "max_attempts": retry_on_timeout_max + 1,
        "current_attempt": 0,
        "attempts_started": 0,
        "attempts_completed": 0,
        "retry_count": 0,
        "timed_out_attempts": 0,
        "next_retry_pending": False,
        "last_exit_code": None,
        "last_timed_out": False,
        "last_started_at": "",
        "last_finished_at": "",
        "archived_attempt_dirs": [],
    }


def archive_attempt_outputs(run_dir: Path, attempt_index: int, case_output_dir: Path | None = None) -> Path:
    archive_dir = run_dir / "attempts" / f"attempt-{attempt_index:02d}"
    archive_dir.mkdir(parents=True, exist_ok=False)
    for name in ATTEMPT_ARCHIVE_FILES:
        source = run_dir / name
        if source.exists() or source.is_symlink():
            shutil.move(str(source), str(archive_dir / name))
    if case_output_dir and case_output_dir.exists():
        shutil.move(str(case_output_dir), str(archive_dir / "case-output"))
    return archive_dir


def refresh_batch_status(python_bin: str, status_script: Path, batch_root: Path) -> None:
    subprocess.run(
        [python_bin, str(status_script), "batch", str(batch_root), "--write", str(batch_root / "batch-status.json")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def parse_trace_env_keys(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_TRACE_ENV_KEYS)
    parts = re.split(r"[\s,:]+", raw.strip())
    return [part for part in parts if part]


def capture_env_snapshot(keys: list[str], source_env: dict[str, str]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for key in keys:
        if key in source_env and source_env[key]:
            snapshot[key] = source_env[key]
    return snapshot


def load_worker_hint(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        try:
            summary = read_json(summary_path)
        except Exception:
            return {}
        return {
            "status": summary.get("status", ""),
            "last_command": summary.get("last_command", ""),
            "last_agent_message": summary.get("last_agent_message", ""),
            "exit_code": summary.get("exit_code"),
        }

    stderr_path = run_dir / "launcher.stderr.log"
    if stderr_path.exists():
        return {"launcher_stderr_tail": stderr_path.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]}

    return {}


def log_batch_error(batch_root: Path, message: str, details: str) -> None:
    launcher_log = batch_root / "launcher.log"
    with launcher_log.open("a", encoding="utf-8") as handle:
        handle.write(f"{now_iso()} ERROR {message}\n")
    write_text(batch_root / "batch-error.txt", details)


def detach_batch(args: argparse.Namespace) -> int:
    manifest_path = args.manifest.resolve()
    batch_root = args.batch_root.resolve()
    batch_root.mkdir(parents=True, exist_ok=True)

    stdout_path = batch_root / "batch-launch.stdout.log"
    stderr_path = batch_root / "batch-launch.stderr.log"
    pid_path = batch_root / "batch.pid"

    cmd = [
        args.python_bin,
        str(Path(__file__).resolve()),
        str(manifest_path),
        str(batch_root),
        "--parallelism",
        str(args.parallelism),
        "--status-interval",
        str(args.status_interval),
        "--python-bin",
        args.python_bin,
    ]
    if args.isolate_home is True:
        cmd.append("--isolate-home")
    elif args.isolate_home is False:
        cmd.append("--no-isolate-home")

    env = os.environ.copy()
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            env=env,
            start_new_session=True,
        )

    write_text(pid_path, f"{proc.pid}\n")
    payload = {
        "detached": True,
        "pid": proc.pid,
        "batch_root": str(batch_root),
        "manifest": str(manifest_path),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }
    write_json(batch_root / "detach-info.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch multiple codex exec workers from a manifest.")
    parser.add_argument("manifest", type=Path, help="JSON or JSONL manifest of jobs.")
    parser.add_argument("batch_root", type=Path, help="Directory where batch outputs should be written.")
    parser.add_argument("--parallelism", type=int, default=int(os.environ.get("CODEX_PARALLELISM", "2")))
    parser.add_argument("--status-interval", type=float, default=float(os.environ.get("CODEX_STATUS_INTERVAL", "5")))
    parser.add_argument("--python-bin", default=sys.executable)
    isolate_group = parser.add_mutually_exclusive_group()
    isolate_group.add_argument(
        "--isolate-home",
        dest="isolate_home",
        action="store_true",
        help="Assign a dedicated CODEX_HOME under <batch-root>/codex-home/<job-id> for jobs that do not set run_home.",
    )
    isolate_group.add_argument(
        "--no-isolate-home",
        dest="isolate_home",
        action="store_false",
        help="Keep using the inherited CODEX_HOME unless a job explicitly sets run_home.",
    )
    parser.set_defaults(isolate_home=None)
    parser.add_argument("--detach", action="store_true", help="Launch the batch in the background and exit after writing batch.pid.")
    return parser


def run_batch(args: argparse.Namespace) -> int:
    manifest_path = args.manifest.resolve()
    batch_root = args.batch_root.resolve()
    batch_root.mkdir(parents=True, exist_ok=True)
    runs_root = batch_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    launcher_log = batch_root / "launcher.log"
    launcher_log.write_text("", encoding="utf-8")

    script_dir = Path(__file__).resolve().parent
    single_script = script_dir / "run_codex_single.sh"
    status_script = script_dir / "codex_status.py"

    manifest_text = manifest_path.read_text(encoding="utf-8", errors="replace")
    write_text(batch_root / "manifest.input.txt", manifest_text)
    jobs = load_jobs(manifest_path)
    if not jobs:
        raise SystemExit("manifest contains no jobs")

    normalized_jobs: list[dict[str, Any]] = []
    attempt_states: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    raw_env_isolate_home = os.environ.get("CODEX_ISOLATE_HOME", "")
    isolate_home = bool(args.isolate_home) if args.isolate_home is not None else False
    isolate_home_source = "cli" if args.isolate_home is not None else "default"
    ignored_env_isolate_home = raw_env_isolate_home if args.isolate_home is None and raw_env_isolate_home not in ("", "0") else ""
    trace_env_keys = parse_trace_env_keys(os.environ.get("CODEX_TRACE_ENV_KEYS"))
    env_trace = capture_env_snapshot(trace_env_keys, os.environ)

    for index, job in enumerate(jobs, start=1):
        raw_id = str(job.get("id") or f"job-{index}")
        job_id = slugify(raw_id)
        if job_id in seen_ids:
            raise SystemExit(f"duplicate job id after normalization: {job_id}")
        seen_ids.add(job_id)

        if not job.get("prompt") and not job.get("prompt_file"):
            raise SystemExit(f"job {job_id} must include prompt or prompt_file")

        run_dir = runs_root / job_id
        if run_dir.exists():
            raise SystemExit(f"run directory already exists: {run_dir}")
        run_dir.mkdir(parents=True)

        prompt_path = run_dir / "prompt.txt"
        if job.get("prompt_file"):
            source = Path(str(job["prompt_file"])).expanduser().resolve()
            if not source.exists():
                raise SystemExit(f"prompt file does not exist for {job_id}: {source}")
            prompt_path.write_text(source.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        else:
            prompt_path.write_text(str(job["prompt"]), encoding="utf-8")

        workdir = Path(str(job.get("workdir") or os.getcwd())).expanduser().resolve()
        extra_configs = job.get("extra_configs") or []
        if not isinstance(extra_configs, list):
            raise SystemExit(f"extra_configs for {job_id} must be a list")
        retry_on_timeout_max = parse_nonnegative_int(
            job.get("retry_on_timeout_max"),
            default=0,
            field_name=f"retry_on_timeout_max for {job_id}",
        )

        extra_configs_path = run_dir / "extra-configs.txt"
        if extra_configs:
            extra_configs_path.write_text("\n".join(str(item) for item in extra_configs) + "\n", encoding="utf-8")

        normalized = {
            "id": job_id,
            "prompt_file": str(prompt_path),
            "source_prompt_file": str(job.get("prompt_file", "")),
            "source_has_inline_prompt": bool(job.get("prompt")),
            "workdir": str(workdir),
            "model": job.get("model", ""),
            "profile": job.get("profile", ""),
            "sandbox": job.get("sandbox", ""),
            "approval_policy": job.get("approval_policy", ""),
            "web_search": job.get("web_search", ""),
            "history_persistence": job.get("history_persistence", ""),
            "output_schema": job.get("output_schema", ""),
            "additional_dirs": job.get("additional_dirs", []),
            "disable_multi_agent": job.get("disable_multi_agent", None),
            "background_terminal_max_timeout": job.get("background_terminal_max_timeout", ""),
            "outer_timeout": job.get("outer_timeout", ""),
            "outer_kill_after": job.get("outer_kill_after", ""),
            "retry_on_timeout_max": retry_on_timeout_max,
            "case_output_dir": str(job.get("case_output_dir", "")),
            "env": job.get("env", {}),
            "run_home": str(job.get("run_home", "")),
            "run_home_source": "job" if job.get("run_home") else "",
            "run_dir": str(run_dir),
        }
        if isolate_home and not normalized["run_home"]:
            normalized["run_home"] = str(batch_root / "codex-home" / job_id)
            normalized["run_home_source"] = "batch-isolate-home"
        elif not normalized["run_home_source"]:
            normalized["run_home_source"] = "inherit"

        write_json(run_dir / "job.json", normalized)
        attempt_state = initial_attempt_state(job_id, retry_on_timeout_max)
        write_json(run_dir / "attempt-state.json", attempt_state)
        attempt_states[job_id] = attempt_state
        normalized_jobs.append(normalized)

    write_jsonl(batch_root / "jobs.jsonl", normalized_jobs)
    write_json(
        batch_root / "batch-config.json",
        {
            "created_at": now_iso(),
            "parallelism": args.parallelism,
            "status_interval": args.status_interval,
            "manifest": str(manifest_path),
            "manifest_input_copy": str(batch_root / "manifest.input.txt"),
            "isolate_home": isolate_home,
            "isolate_home_source": isolate_home_source,
            "ignored_env_isolate_home": ignored_env_isolate_home,
            "python_bin": args.python_bin,
            "cwd": os.getcwd(),
            "launcher_pid": os.getpid(),
            "trace_env_keys": trace_env_keys,
            "env_trace": env_trace,
        },
    )

    pending: deque[dict[str, Any]] = deque(normalized_jobs)
    running: dict[str, dict[str, Any]] = {}
    exit_codes: dict[str, int] = {}

    def log(message: str) -> None:
        with launcher_log.open("a", encoding="utf-8") as handle:
            handle.write(f"{now_iso()} {message}\n")

    if ignored_env_isolate_home:
        log(
            "ignored CODEX_ISOLATE_HOME from environment because home isolation is now opt-in; "
            "use --isolate-home or per-job run_home to enable it"
        )

    def launch(job: dict[str, Any]) -> None:
        run_dir = Path(job["run_dir"])
        attempt_state = attempt_states[job["id"]]
        attempt_state["attempts_started"] += 1
        attempt_state["current_attempt"] = attempt_state["attempts_started"]
        attempt_state["next_retry_pending"] = False
        attempt_state["last_exit_code"] = None
        attempt_state["last_timed_out"] = False
        attempt_state["last_started_at"] = now_iso()
        write_json(run_dir / "attempt-state.json", attempt_state)

        env = os.environ.copy()
        env.update({key: str(value) for key, value in (job.get("env") or {}).items()})

        def set_if_present(env_key: str, value: Any) -> None:
            if value not in (None, ""):
                env[env_key] = str(value)

        set_if_present("CODEX_MODEL", job.get("model"))
        set_if_present("CODEX_PROFILE", job.get("profile"))
        set_if_present("CODEX_SANDBOX", job.get("sandbox"))
        set_if_present("CODEX_APPROVAL_POLICY", job.get("approval_policy"))
        set_if_present("CODEX_WEB_SEARCH", job.get("web_search"))
        set_if_present("CODEX_HISTORY_PERSISTENCE", job.get("history_persistence"))
        set_if_present("CODEX_OUTPUT_SCHEMA", job.get("output_schema"))
        set_if_present("CODEX_BACKGROUND_TERMINAL_MAX_TIMEOUT", job.get("background_terminal_max_timeout"))
        set_if_present("CODEX_OUTER_TIMEOUT", job.get("outer_timeout"))
        set_if_present("CODEX_OUTER_KILL_AFTER", job.get("outer_kill_after"))
        set_if_present("CODEX_RUN_HOME", job.get("run_home"))
        set_if_present("CODEX_CASE_OUTPUT_DIR", job.get("case_output_dir"))
        env["CODEX_ATTEMPT_NUMBER"] = str(attempt_state["current_attempt"])
        env["CODEX_MAX_ATTEMPTS"] = str(attempt_state["max_attempts"])
        env["CODEX_RETRY_ON_TIMEOUT_MAX"] = str(attempt_state["retry_on_timeout_max"])

        disable_multi_agent = job.get("disable_multi_agent")
        if disable_multi_agent is not None:
            env["CODEX_DISABLE_MULTI_AGENT"] = "1" if bool(disable_multi_agent) else "0"

        additional_dirs = job.get("additional_dirs") or []
        if additional_dirs:
            env["CODEX_ADDITIONAL_DIRS"] = ":".join(str(Path(str(item)).expanduser()) for item in additional_dirs)

        extra_configs_path = run_dir / "extra-configs.txt"
        if extra_configs_path.exists():
            env["CODEX_EXTRA_CONFIGS_FILE"] = str(extra_configs_path)

        launcher_stdout = (run_dir / "launcher.stdout.log").open("w", encoding="utf-8")
        launcher_stderr = (run_dir / "launcher.stderr.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [str(single_script), str(run_dir / "prompt.txt"), str(run_dir), str(job["workdir"])],
            stdout=launcher_stdout,
            stderr=launcher_stderr,
            text=True,
            env=env,
        )
        launcher_stdout.close()
        launcher_stderr.close()
        running[job["id"]] = {"proc": proc, "job": job}
        log(
            f"started {job['id']} pid={proc.pid} attempt={attempt_state['current_attempt']}/{attempt_state['max_attempts']}"
        )

    refresh_batch_status(args.python_bin, status_script, batch_root)

    while pending or running:
        while pending and len(running) < args.parallelism:
            launch(pending.popleft())

        time.sleep(args.status_interval)
        refresh_batch_status(args.python_bin, status_script, batch_root)

        finished_ids: list[str] = []
        for job_id, running_info in running.items():
            proc = running_info["proc"]
            job = running_info["job"]
            rc = proc.poll()
            if rc is None:
                continue
            run_dir = Path(job["run_dir"])
            attempt_state = attempt_states[job_id]
            result_marker = parse_result_marker(run_dir / "result.txt")
            timed_out = did_attempt_timeout(job, rc, result_marker)
            attempt_index = int(attempt_state.get("current_attempt") or 0)
            hint = load_worker_hint(run_dir)
            attempt_state["attempts_completed"] = max(attempt_state["attempts_completed"], attempt_index)
            attempt_state["last_exit_code"] = rc
            attempt_state["last_timed_out"] = timed_out
            attempt_state["last_finished_at"] = now_iso()
            if timed_out:
                attempt_state["timed_out_attempts"] += 1

            history_entry: dict[str, Any] = {
                "attempt": attempt_index,
                "finished_at": attempt_state["last_finished_at"],
                "exit_code": rc,
                "timed_out": timed_out,
                "result_marker": result_marker,
            }

            should_retry = timed_out and attempt_state["retry_count"] < attempt_state["retry_on_timeout_max"]
            if should_retry:
                case_output_dir = None
                if job.get("case_output_dir"):
                    case_output_dir = Path(str(job["case_output_dir"])).expanduser().resolve()
                archive_dir = archive_attempt_outputs(run_dir, attempt_index, case_output_dir=case_output_dir)
                history_entry["archived_to"] = str(archive_dir)
                append_jsonl(run_dir / "attempt-history.jsonl", history_entry)
                attempt_state["retry_count"] += 1
                attempt_state["next_retry_pending"] = True
                attempt_state["archived_attempt_dirs"].append(str(archive_dir))
                write_json(run_dir / "attempt-state.json", attempt_state)
                pending.appendleft(job)
                if hint:
                    log(
                        "retrying "
                        f"{job_id} after timeout exit_code={rc} attempt={attempt_index}/{attempt_state['max_attempts']} "
                        f"next_attempt={attempt_index + 1}/{attempt_state['max_attempts']} hint={json.dumps(hint, ensure_ascii=False)}"
                    )
                else:
                    log(
                        "retrying "
                        f"{job_id} after timeout exit_code={rc} attempt={attempt_index}/{attempt_state['max_attempts']} "
                        f"next_attempt={attempt_index + 1}/{attempt_state['max_attempts']}"
                    )
            else:
                exit_codes[job_id] = rc
                append_jsonl(run_dir / "attempt-history.jsonl", history_entry)
                attempt_state["next_retry_pending"] = False
                write_json(run_dir / "attempt-state.json", attempt_state)
            finished_ids.append(job_id)
            if not should_retry:
                if hint:
                    log(f"finished {job_id} exit_code={rc} hint={json.dumps(hint, ensure_ascii=False)}")
                else:
                    log(f"finished {job_id} exit_code={rc}")

        for job_id in finished_ids:
            running.pop(job_id, None)

    refresh_batch_status(args.python_bin, status_script, batch_root)
    subprocess.run(
        [args.python_bin, str(status_script), "batch", str(batch_root), "--write", str(batch_root / "batch-results.json")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    final_payload = json.loads((batch_root / "batch-results.json").read_text(encoding="utf-8"))
    final_payload["launcher_exit_codes"] = exit_codes
    write_json(batch_root / "batch-results.json", final_payload)

    print(json.dumps(final_payload, ensure_ascii=False, indent=2))
    return 0 if all(code == 0 for code in exit_codes.values()) else 1


def main() -> int:
    args = build_parser().parse_args()
    if args.detach:
        return detach_batch(args)

    batch_root = args.batch_root.resolve()
    try:
        return run_batch(args)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        batch_root.mkdir(parents=True, exist_ok=True)
        details = traceback.format_exc()
        log_batch_error(batch_root, str(exc), details)
        print(details, file=sys.stderr)
        if isinstance(exc, SystemExit) and isinstance(exc.code, int):
            return exc.code
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
