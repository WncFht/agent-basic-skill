from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path


class ExitCode(IntEnum):
    SUCCESS = 0
    INPUT_ERROR = 1
    LINT_FAILED = 2
    BUILD_FAILED = 3
    DEPENDENCY_MISSING = 4


@dataclass(frozen=True)
class CommandResult:
    command: str
    status: str
    exit_code: int
    fields: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FetchResult:
    workspace: Path
    arxiv_id: str
    paper_id_with_version: str
    title: str | None
    source_url: str
    archive_path: Path | None
    preprocessed_tex_files: int
    removed_comment_lines: int
    collapsed_blank_lines: int
    binhex_status: str


@dataclass(frozen=True)
class GeneratedEntryResult:
    main_tex: Path
    entry_path: Path
    preamble_path: Path
    notes_enabled: bool


@dataclass(frozen=True)
class SetupResult:
    workspace: Path
    main_tex: Path
    entry_path: Path
    preamble_path: Path
    notes_enabled: bool
    removed_generated_paths: tuple[Path, ...]


@dataclass(frozen=True)
class LintIssue:
    path: Path
    line: int
    kind: str
    message: str


@dataclass(frozen=True)
class LintResult:
    workspace: Path
    checked_files: tuple[Path, ...]
    issues: tuple[LintIssue, ...]


@dataclass(frozen=True)
class BuildPlan:
    workspace: Path
    targets: tuple[Path, ...]
    quick: bool
    refresh_entry: bool
    skip_lint: bool


@dataclass(frozen=True)
class BuildPassResult:
    label: str
    command: tuple[str, ...]
    output: str


@dataclass(frozen=True)
class FatalDiagnosis:
    code: str
    summary: tuple[str, ...]
    advice: tuple[str, ...]
    should_retry_with_aux_cleanup: bool = False


@dataclass(frozen=True)
class FloatHit:
    path: Path
    line: int
    env_name: str


@dataclass(frozen=True)
class VisualCheckResult:
    pdf: Path
    preview_dir: Path | None
    rendered_pages: int
    risky_floats: tuple[FloatHit, ...]
    status: str
    note: str


@dataclass(frozen=True)
class BuildTargetResult:
    tex: Path
    pdf: Path | None
    log: Path
    compiler: str
    mode: str
    has_bibtex: bool
    binhex_status: str
    removed_stale_aux: tuple[Path, ...]
    warnings: tuple[str, ...]
    pass_results: tuple[BuildPassResult, ...]
    fatal: FatalDiagnosis | None
    status: str


@dataclass(frozen=True)
class BuildResult:
    workspace: Path
    plan: BuildPlan
    lint_result: LintResult | None
    refreshed_entry: GeneratedEntryResult | None
    refresh_reason: str | None
    targets: tuple[BuildTargetResult, ...]
    status: str
    exit_code: int


@dataclass(frozen=True)
class ToolCheck:
    name: str
    found: bool
    path: str | None
    note: str | None = None


@dataclass(frozen=True)
class DoctorResult:
    workspace: Path | None
    tools: tuple[ToolCheck, ...]
    python_modules: tuple[ToolCheck, ...]
    workspace_status: str | None
    notes: tuple[str, ...]
