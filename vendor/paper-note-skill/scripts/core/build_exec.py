from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from core.build_plan import (
    cleanup_stale_aux_files,
    detect_log_path,
    detect_pdf_path,
    make_build_plan,
    needs_bibtex,
)
from core.build_report import (
    diagnose_fatal,
    should_rerun_latex,
    summarize_final_warnings,
    summarize_quick_warnings,
)
from core.entry import refresh_generated_entry
from core.latex_compat import ensure_binhex_compat
from core.lint_rules import lint_workspace
from core.models import (
    BuildPassResult,
    BuildResult,
    BuildTargetResult,
    ExitCode,
    FatalDiagnosis,
)
from core.workspace import (
    ENTRY_FILE_NAME,
    detect_compiler,
    detect_main_tex,
    needs_entry_refresh,
    resolve_existing_directory,
)

ALLOWED_COMPILERS = {"pdflatex", "xelatex", "lualatex"}


class CommandFailure(RuntimeError):
    def __init__(self, result: BuildPassResult):
        super().__init__(result.label)
        self.result = result


def append_log(log_path: Path, label: str, command: list[str], output: str) -> None:
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"== {label}: {' '.join(command)} ==\n")
        handle.write(output)
        if output and not output.endswith("\n"):
            handle.write("\n")
        handle.write("\n")


def run_command(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    label: str,
) -> BuildPassResult:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = result.stdout + result.stderr
    command_result = BuildPassResult(
        label=label,
        command=tuple(command),
        output=output,
    )
    append_log(log_path, label, command, output)
    if result.returncode != 0:
        raise CommandFailure(command_result)
    return command_result


def missing_dependency_target(
    *,
    tex_file: Path,
    log_path: Path,
    compiler: str,
    mode: str,
    has_bibtex: bool,
    binhex_status: str,
    missing_tools: list[str],
) -> BuildTargetResult:
    missing_list = ", ".join(missing_tools)
    fatal = FatalDiagnosis(
        code="missing-dependency",
        summary=(f"Missing required tools: {missing_list}",),
        advice=(f"安装或暴露这些命令到 PATH: {missing_list}",),
    )
    return BuildTargetResult(
        tex=tex_file,
        pdf=None,
        log=log_path,
        compiler=compiler,
        mode=mode,
        has_bibtex=has_bibtex,
        binhex_status=binhex_status,
        removed_stale_aux=(),
        warnings=(),
        pass_results=(),
        fatal=fatal,
        status="missing_dependency",
    )


def invalid_compiler_target(
    *,
    tex_file: Path,
    log_path: Path,
    compiler: str,
    mode: str,
    has_bibtex: bool,
    binhex_status: str,
) -> BuildTargetResult:
    fatal = FatalDiagnosis(
        code="unsupported-compiler",
        summary=(f"Unsupported compiler in 00README.json: {compiler}",),
        advice=("只支持 pdflatex / xelatex / lualatex。",),
    )
    return BuildTargetResult(
        tex=tex_file,
        pdf=None,
        log=log_path,
        compiler=compiler,
        mode=mode,
        has_bibtex=has_bibtex,
        binhex_status=binhex_status,
        removed_stale_aux=(),
        warnings=(),
        pass_results=(),
        fatal=fatal,
        status="invalid_compiler",
    )


def compile_target(
    workspace: Path, tex_file: Path, *, quick: bool
) -> BuildTargetResult:
    compiler = detect_compiler(workspace)
    has_bibtex = needs_bibtex(tex_file)
    mode = "quick" if quick else "full"
    log_path = detect_log_path(workspace, tex_file)
    log_path.write_text("", encoding="utf-8")
    removed_aux_files = cleanup_stale_aux_files(workspace, tex_file)
    binhex_status = ensure_binhex_compat(workspace)

    if compiler not in ALLOWED_COMPILERS:
        return invalid_compiler_target(
            tex_file=tex_file,
            log_path=log_path,
            compiler=compiler,
            mode=mode,
            has_bibtex=has_bibtex,
            binhex_status=binhex_status,
        )

    required_tools = [compiler]
    if has_bibtex and not quick:
        required_tools.append("bibtex")
    missing_tools = [tool for tool in required_tools if shutil.which(tool) is None]
    if missing_tools:
        return missing_dependency_target(
            tex_file=tex_file,
            log_path=log_path,
            compiler=compiler,
            mode=mode,
            has_bibtex=has_bibtex,
            binhex_status=binhex_status,
            missing_tools=missing_tools,
        )

    compile_args = [
        compiler,
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex_file.name,
    ]
    outputs: list[str] = []
    pass_results: list[BuildPassResult] = []
    aux_retry_removed_files: list[Path] = []

    def run_compile_sequence() -> None:
        preflight = run_command(
            compile_args,
            cwd=workspace,
            log_path=log_path,
            label="latex-preflight",
        )
        pass_results.append(preflight)
        outputs.append(preflight.output)

        if quick:
            return

        if has_bibtex:
            bibtex_result = run_command(
                ["bibtex", tex_file.stem],
                cwd=workspace,
                log_path=log_path,
                label="bibtex",
            )
            pass_results.append(bibtex_result)
            outputs.append(bibtex_result.output)
            for label in ("latex-pass-2", "latex-pass-3"):
                latex_result = run_command(
                    compile_args,
                    cwd=workspace,
                    log_path=log_path,
                    label=label,
                )
                pass_results.append(latex_result)
                outputs.append(latex_result.output)
            if should_rerun_latex(outputs[-1]):
                latex_result = run_command(
                    compile_args,
                    cwd=workspace,
                    log_path=log_path,
                    label="latex-pass-4",
                )
                pass_results.append(latex_result)
                outputs.append(latex_result.output)
            return

        latex_result = run_command(
            compile_args,
            cwd=workspace,
            log_path=log_path,
            label="latex-pass-2",
        )
        pass_results.append(latex_result)
        outputs.append(latex_result.output)
        if should_rerun_latex(latex_result.output):
            latex_result = run_command(
                compile_args,
                cwd=workspace,
                log_path=log_path,
                label="latex-pass-3",
            )
            pass_results.append(latex_result)
            outputs.append(latex_result.output)

    try:
        run_compile_sequence()
    except CommandFailure as error:
        diagnosis = diagnose_fatal(error.result.output)
        if diagnosis.should_retry_with_aux_cleanup:
            aux_retry_removed_files = cleanup_stale_aux_files(
                workspace,
                tex_file,
                include_aux=True,
            )
            outputs.clear()
            pass_results.clear()
            append_log(
                log_path,
                "paper-note-recovery",
                ["cleanup-aux-retry"],
                "Detected likely Unicode aux/bookmark state. Removed stale aux files and retried.",
            )
            try:
                run_compile_sequence()
            except CommandFailure as retry_error:
                retry_diagnosis = diagnose_fatal(retry_error.result.output)
                return BuildTargetResult(
                    tex=tex_file,
                    pdf=None,
                    log=log_path,
                    compiler=compiler,
                    mode=mode,
                    has_bibtex=has_bibtex,
                    binhex_status=binhex_status,
                    removed_stale_aux=tuple(
                        removed_aux_files + aux_retry_removed_files
                    ),
                    warnings=summarize_final_warnings(
                        outputs + [retry_error.result.output]
                    ),
                    pass_results=tuple(pass_results),
                    fatal=retry_diagnosis,
                    status=f"failed at {retry_error.result.label}",
                )
        else:
            return BuildTargetResult(
                tex=tex_file,
                pdf=None,
                log=log_path,
                compiler=compiler,
                mode=mode,
                has_bibtex=has_bibtex,
                binhex_status=binhex_status,
                removed_stale_aux=tuple(removed_aux_files),
                warnings=summarize_final_warnings(outputs + [error.result.output]),
                pass_results=tuple(pass_results),
                fatal=diagnosis,
                status=f"failed at {error.result.label}",
            )

    if quick:
        return BuildTargetResult(
            tex=tex_file,
            pdf=None,
            log=log_path,
            compiler=compiler,
            mode=mode,
            has_bibtex=has_bibtex,
            binhex_status=binhex_status,
            removed_stale_aux=tuple(removed_aux_files + aux_retry_removed_files),
            warnings=summarize_quick_warnings(outputs, has_bibtex=has_bibtex),
            pass_results=tuple(pass_results),
            fatal=None,
            status="quick_checked",
        )

    return BuildTargetResult(
        tex=tex_file,
        pdf=detect_pdf_path(workspace, tex_file),
        log=log_path,
        compiler=compiler,
        mode=mode,
        has_bibtex=has_bibtex,
        binhex_status=binhex_status,
        removed_stale_aux=tuple(removed_aux_files + aux_retry_removed_files),
        warnings=summarize_final_warnings(outputs),
        pass_results=tuple(pass_results),
        fatal=None,
        status="compiled",
    )


def build_workspace(
    workspace: Path,
    *,
    tex: str | None = None,
    quick: bool = False,
    refresh_entry: bool = False,
    skip_lint: bool = False,
) -> BuildResult:
    workspace = resolve_existing_directory(str(workspace), label="workspace")
    plan = make_build_plan(
        workspace,
        tex=tex,
        quick=quick,
        refresh_entry=refresh_entry,
        skip_lint=skip_lint,
    )

    refreshed_entry = None
    refresh_reason = None
    entry_path = workspace / ENTRY_FILE_NAME
    if entry_path in plan.targets and entry_path.exists():
        main_tex = detect_main_tex(workspace)
        if refresh_entry:
            refreshed_entry = refresh_generated_entry(workspace, main_tex=main_tex)
            refresh_reason = "requested"
        elif needs_entry_refresh(entry_path, main_tex):
            refreshed_entry = refresh_generated_entry(workspace, main_tex=main_tex)
            refresh_reason = "main_tex_newer"

    lint_result = None
    if not plan.skip_lint:
        lint_result = lint_workspace(workspace)
        if lint_result.issues:
            return BuildResult(
                workspace=workspace,
                plan=plan,
                lint_result=lint_result,
                refreshed_entry=refreshed_entry,
                refresh_reason=refresh_reason,
                targets=(),
                status="lint_failed",
                exit_code=int(ExitCode.LINT_FAILED),
            )

    targets = tuple(
        compile_target(workspace, tex_file, quick=plan.quick)
        for tex_file in plan.targets
    )
    statuses = {target.status for target in targets}
    if any(status == "invalid_compiler" for status in statuses):
        overall_status = "invalid_input"
        exit_code = int(ExitCode.INPUT_ERROR)
    elif any(status == "missing_dependency" for status in statuses):
        overall_status = "missing_dependency"
        exit_code = int(ExitCode.DEPENDENCY_MISSING)
    elif any(status.startswith("failed at ") for status in statuses):
        overall_status = "failed"
        exit_code = int(ExitCode.BUILD_FAILED)
    else:
        overall_status = "quick_checked" if plan.quick else "compiled"
        exit_code = int(ExitCode.SUCCESS)

    return BuildResult(
        workspace=workspace,
        plan=plan,
        lint_result=lint_result,
        refreshed_entry=refreshed_entry,
        refresh_reason=refresh_reason,
        targets=targets,
        status=overall_status,
        exit_code=exit_code,
    )
