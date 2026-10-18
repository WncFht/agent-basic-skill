from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

CONFIG_DIR_NAME = ".paper-note-skill"
CONFIG_FILE_NAME = "config.yaml"
OUTPUT_ROOT_ENV_VAR = "PAPER_NOTE_OUTPUT_ROOT"
OUTPUT_ROOT_KEY = "output_root"


@dataclass(frozen=True)
class PaperNoteConfig:
    output_root: str | None = None


@dataclass(frozen=True)
class OutputRootResolution:
    root: Path
    source: str
    config_path: Path


def config_dir_path() -> Path:
    return Path.home() / CONFIG_DIR_NAME


def config_path() -> Path:
    return config_dir_path() / CONFIG_FILE_NAME


def strip_optional_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_simple_yaml_mapping(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = strip_optional_quotes(value)
    return values


def load_config(path: Path | None = None) -> PaperNoteConfig:
    target = config_path() if path is None else path
    if not target.exists():
        return PaperNoteConfig()
    values = parse_simple_yaml_mapping(target.read_text(encoding="utf-8"))
    output_root = values.get(OUTPUT_ROOT_KEY, "").strip() or None
    return PaperNoteConfig(output_root=output_root)


def save_config(config: PaperNoteConfig, path: Path | None = None) -> Path:
    target = config_path() if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# paper-note-skill user config"]
    if config.output_root:
        lines.append(f"{OUTPUT_ROOT_KEY}: {config.output_root}")
    payload = "\n".join(lines) + "\n"
    target.write_text(payload, encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def normalize_output_root(raw_path: str, *, repo_root: Path) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def resolve_output_root(
    *,
    repo_root: Path,
    fallback_root: Path,
    environ: Mapping[str, str] | None = None,
    path: Path | None = None,
) -> OutputRootResolution:
    active_environ = os.environ if environ is None else environ
    target_config_path = config_path() if path is None else path

    raw_path = active_environ.get(OUTPUT_ROOT_ENV_VAR, "").strip()
    if raw_path:
        return OutputRootResolution(
            root=normalize_output_root(raw_path, repo_root=repo_root),
            source="env",
            config_path=target_config_path,
        )

    config = load_config(target_config_path)
    if config.output_root:
        return OutputRootResolution(
            root=normalize_output_root(config.output_root, repo_root=repo_root),
            source="config",
            config_path=target_config_path,
        )

    return OutputRootResolution(
        root=fallback_root,
        source="fallback",
        config_path=target_config_path,
    )
