"""Run-level logging for the paper-search CLI."""

from __future__ import annotations

import json
import shlex
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from _artifacts import artifact_root

WARNING_DIAGNOSTICS = frozenset(
    {
        "CandidateScanTruncated",
        "IdNotFound",
        "ResultLimitAdjusted",
        "VenueDiscoveryEmpty",
    }
)


def _diagnostic_severity(item: dict) -> str:
    return "warning" if item.get("type") in WARNING_DIAGNOSTICS else "error"


class _Tee:
    def __init__(self, original, log_handle):
        self.original = original
        self.log_handle = log_handle

    def write(self, text):
        self.original.write(text)
        self.log_handle.write(text)
        self.log_handle.flush()

    def flush(self):
        self.original.flush()
        self.log_handle.flush()

    def isatty(self):
        return self.original.isatty()


class RunLogger:
    """Persist a command summary and a copy of the CLI stderr stream."""

    def __init__(self, base_dir: Path | None = None):
        now = datetime.now(timezone.utc)
        run_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        root = base_dir or artifact_root() / "paper-search-logs"
        self.path = root / now.strftime("%Y-%m") / run_id
        self.path.mkdir(parents=True, exist_ok=False)
        self.started_at = now
        self.started_monotonic = time.monotonic()
        self.stderr_path = self.path / "stderr.log"
        self._stderr_handle = self.stderr_path.open("w", encoding="utf-8")
        self.tee = _Tee(sys.stderr, self._stderr_handle)

    def write_summary(
        self,
        *,
        argv: list[str],
        report: dict | None,
        report_path: Path | None,
        exit_code: int,
        exception: BaseException | None = None,
    ) -> Path:
        finished = datetime.now(timezone.utc)
        errors = (report or {}).get("errors", {})
        per_source = (report or {}).get("stats", {}).get("per_source_hits", {})
        runtime = (report or {}).get("runtime", {})
        source_summary = {}
        for source, count in per_source.items():
            diagnostics = list(errors.get(source) or [])
            logged_diagnostics = [
                {
                    "severity": _diagnostic_severity(item),
                    "query": item.get("query"),
                    "type": item.get("type"),
                    "message": item.get("message"),
                }
                for item in diagnostics
            ]
            has_errors = any(item["severity"] == "error" for item in logged_diagnostics)
            if has_errors:
                source_status = "partial" if count else "failed"
            elif logged_diagnostics:
                source_status = "warning"
            else:
                source_status = "success"
            source_summary[source] = {
                "status": source_status,
                "papers": count,
                "diagnostics": len(diagnostics),
                "diagnostic_details": logged_diagnostics,
                "duration_seconds": runtime.get(source, {}).get("duration_seconds"),
                "worker_exit_code": runtime.get(source, {}).get("worker_exit_code"),
            }
        if exception is not None:
            status = (
                "interrupted" if isinstance(exception, KeyboardInterrupt) else "failed"
            )
        elif any(
            item["status"] in {"failed", "partial"} for item in source_summary.values()
        ):
            status = "partial"
        elif any(item["status"] == "warning" for item in source_summary.values()):
            status = "warning"
        else:
            status = "success"
        payload = {
            "schema_version": 1,
            "run_id": self.path.name,
            "started_at": self.started_at.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_seconds": round(time.monotonic() - self.started_monotonic, 3),
            "status": status,
            "argv": list(argv),
            "command": shlex.join(argv),
            "request": (report or {}).get("request", {}),
            "sources": source_summary,
            "unique_papers": (report or {}).get("stats", {}).get("unique_papers"),
            "report_path": str(report_path) if report_path else None,
            "stderr_path": str(self.stderr_path),
            "exit_code": exit_code,
        }
        if exception is not None:
            payload["exception"] = {
                "type": type(exception).__name__,
                "message": str(exception),
            }
        summary_path = self.path / "run.json"
        summary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return summary_path

    def close(self):
        self._stderr_handle.close()
