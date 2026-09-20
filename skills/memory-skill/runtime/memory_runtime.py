#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


DEFAULT_MEMORY_ROOT = Path.home() / ".codex" / "memory"
STATE_FILE = Path.home() / ".codex" / "state" / "memory-skill" / "state.json"
TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "templates" / "memory-tree"
SOCKS_PROXY_COMMAND = Path(__file__).resolve().with_name("ssh_via_socks.py")
DEFAULT_COMMIT_MESSAGE = "chore(memory): update memory packs"
SOCKS5_NO_AUTH_GREETING = b"\x05\x01\x00"
SOCKS5_NO_AUTH_ACCEPT = b"\x05\x00"


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise MemoryRuntimeError(
            what=f"Environment variable `{name}` is not a valid number.",
            why="The memory runtime uses this setting to control sync timing.",
            fix=f"Unset `{name}` or assign it a numeric value such as `{default}`.",
            details=[f"Received value: {value!r}"],
        ) from exc


HEARTBEAT_INTERVAL_SECONDS = env_float("MEMORY_SYNC_HEARTBEAT_SECONDS", 2.0)
STALE_AFTER_SECONDS = env_float("MEMORY_SYNC_STALE_AFTER_SECONDS", 30.0)
WAIT_TIMEOUT_SECONDS = env_float("MEMORY_SYNC_WAIT_TIMEOUT_SECONDS", 300.0)
WAIT_POLL_SECONDS = env_float("MEMORY_SYNC_WAIT_POLL_SECONDS", 0.2)
REMOTE_RETRY_ATTEMPTS = 3
REMOTE_RETRY_BASE_DELAY_SECONDS = 1.0
GITHUB_TOKEN_ENV_VARS = ("MEMORY_SYNC_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
GITHUB_REMOTE_HOSTS = {"github.com", "ssh.github.com"}
SOCKS_PROXY_ENV_VARS = ("MEMORY_SYNC_SOCKS_PROXY", "ALL_PROXY", "all_proxy")
GENERIC_PROXY_ENV_VARS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
)
DEFAULT_LOCAL_SOCKS_PROXIES = (
    "socks5://127.0.0.1:7897",
    "socks5h://127.0.0.1:7891",
)
TRANSIENT_REMOTE_ERROR_MARKERS = (
    "connection closed by",
    "connection reset by peer",
    "operation timed out",
    "timed out",
    "could not resolve host",
    "couldn't connect to server",
    "failed to connect to",
    "failure when receiving data from the peer",
    "early eof",
    "unexpected disconnect",
    "remote end hung up unexpectedly",
    "tls connect error",
    "unexpected eof while reading",
    "ssh_exchange_identification",
    "kex_exchange_identification",
)
AUTH_REMOTE_ERROR_MARKERS = (
    "401 unauthorized",
    "403 forbidden",
    "authentication failed",
    "could not read username",
    "could not read password",
    "repository not found",
    "access denied",
)


@dataclass
class MemoryRuntimeError(Exception):
    what: str
    why: str
    fix: str
    details: list[str] = field(default_factory=list)
    exit_code: int = 1


@dataclass(frozen=True)
class RemoteExecutionPlan:
    label: str
    prefix_args: tuple[str, ...] = ()
    env_overrides: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()
    include_ssh_proxy_command: bool = True


@dataclass(frozen=True)
class HostIdentity:
    raw: str
    normalized: str
    source: str


class FriendlyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise MemoryRuntimeError(
            what="The memory command arguments were not valid.",
            why="The runtime could not determine which operation or memory root to use.",
            fix=f"{message}\n\n{self.format_help()}",
            exit_code=2,
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def normalize_machine_hostname(value: str) -> str:
    cleaned = value.strip()
    if cleaned.lower().endswith(".local"):
        cleaned = cleaned[:-6]
    cleaned = re.sub(r"[^0-9A-Za-z]+", "-", cleaned.lower()).strip("-")
    return cleaned


def detect_host_identity(env: Mapping[str, str] | None = None) -> HostIdentity:
    source_env = env or os.environ
    candidates: list[tuple[str, str]] = []

    def add_candidate(source: str, value: str | None) -> None:
        if value is None:
            return
        cleaned = value.strip()
        if cleaned:
            candidates.append((source, cleaned))

    with contextlib.suppress(OSError):
        add_candidate("socket.gethostname()", socket.gethostname())
    with contextlib.suppress(OSError):
        add_candidate("platform.node()", platform.node())
    if hasattr(os, "uname"):
        with contextlib.suppress(OSError, AttributeError):
            add_candidate("os.uname().nodename", os.uname().nodename)
    add_candidate("HOSTNAME", source_env.get("HOSTNAME"))
    add_candidate("COMPUTERNAME", source_env.get("COMPUTERNAME"))

    seen: set[str] = set()
    for source, raw in candidates:
        normalized = normalize_machine_hostname(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        return HostIdentity(raw=raw, normalized=normalized, source=source)

    raise MemoryRuntimeError(
        what="Could not determine the current machine hostname.",
        why="Machine memory routing depends on a stable local host identifier.",
        fix="Ensure Python can resolve the local hostname, or export `HOSTNAME` or `COMPUTERNAME`, then retry.",
    )


def same_machine_hostname(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    left_normalized = normalize_machine_hostname(left)
    right_normalized = normalize_machine_hostname(right)
    if left_normalized and right_normalized:
        return left_normalized == right_normalized
    return left.strip() == right.strip()


def print_failure(error: MemoryRuntimeError) -> None:
    print("memory runtime error", file=sys.stderr)
    print(f"What happened: {error.what}", file=sys.stderr)
    print(f"Why it matters: {error.why}", file=sys.stderr)
    print(f"How to fix: {error.fix}", file=sys.stderr)
    for detail in error.details:
        print(f"Detail: {detail}", file=sys.stderr)


def print_success(title: str, lines: list[str]) -> None:
    print(title)
    for line in lines:
        print(f"- {line}")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise MemoryRuntimeError(
            what=f"State file `{path}` is not valid JSON.",
            why="The runtime cannot safely resolve the active memory root from a corrupted state file.",
            fix="Delete or repair the state file, then re-run `init-memory` or pass `--memory-root` explicitly.",
            details=[str(exc)],
        ) from exc


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_saved_root() -> Path | None:
    if not STATE_FILE.exists():
        return None
    payload = read_json(STATE_FILE)
    raw_root = payload.get("memory_root")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise MemoryRuntimeError(
            what=f"State file `{STATE_FILE}` is missing `memory_root`.",
            why="The runtime cannot determine which repo to use for memory operations.",
            fix="Run `init-memory --memory-root <path>` again or remove the invalid state file.",
        )
    return Path(raw_root).expanduser()


def save_active_root(root: Path) -> None:
    payload = {
        "memory_root": str(root),
        "saved_at": iso_now(),
        "platform": sys.platform,
    }
    write_json(STATE_FILE, payload)


def resolve_memory_root(cli_value: str | None) -> tuple[Path, str]:
    if cli_value:
        return Path(cli_value).expanduser(), "--memory-root"

    env_value = os.environ.get("MEMORY_ROOT")
    if env_value:
        return Path(env_value).expanduser(), "MEMORY_ROOT"

    saved_root = load_saved_root()
    if saved_root:
        return saved_root, str(STATE_FILE)

    return DEFAULT_MEMORY_ROOT, "default"


def required_memory_paths(root: Path) -> dict[str, Path]:
    return {
        "core.md": root / "core.md",
        "rules.md": root / "rules.md",
        "machines/index.md": root / "machines" / "index.md",
        "repos/index.md": root / "repos" / "index.md",
        "topics/": root / "topics",
    }


def validate_memory_tree(root: Path) -> None:
    missing: list[str] = []
    for label, path in required_memory_paths(root).items():
        if label.endswith("/"):
            if not path.is_dir():
                missing.append(label)
        else:
            if not path.is_file():
                missing.append(label)
    if missing:
        raise MemoryRuntimeError(
            what=f"`{root}` is not a valid memory repo layout.",
            why="Sync and bootstrap commands need the standard memory tree to read and write packs safely.",
            fix="Run `init-memory --memory-root <path>` to create a new repo or choose an existing valid memory repo.",
            details=[f"Missing entries: {', '.join(missing)}"],
        )


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = True,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=capture_output,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MemoryRuntimeError(
            what=f"Required executable `{args[0]}` is not available.",
            why="The memory runtime depends on external tools for repo operations.",
            fix=f"Install `{args[0]}` or add it to PATH, then retry the command.",
        ) from exc

    if check and completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise MemoryRuntimeError(
            what=f"Command `{' '.join(args)}` failed.",
            why="The requested memory operation could not complete successfully.",
            fix="Review the command output and correct the repo state before retrying.",
            details=[stderr] if stderr else [],
        )

    return completed


def proxy_host_port(proxy_url: str) -> tuple[str, int] | None:
    parsed = urlsplit(proxy_url)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return None
    return host, port


def supports_socks5_no_auth(proxy_url: str, timeout: float = 0.2) -> bool:
    host_port = proxy_host_port(proxy_url)
    if host_port is None:
        return False

    try:
        with socket.create_connection(host_port, timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(SOCKS5_NO_AUTH_GREETING)
            return sock.recv(2) == SOCKS5_NO_AUTH_ACCEPT
    except OSError:
        return False


def has_configured_proxy_env(env: Mapping[str, str] | None = None) -> bool:
    source = env or os.environ
    return any(source.get(name, "").strip() for name in GENERIC_PROXY_ENV_VARS)


def explicit_socks_proxy_url(env: Mapping[str, str] | None = None) -> str | None:
    source = env or os.environ
    for name in SOCKS_PROXY_ENV_VARS:
        value = source.get(name)
        if value and value.strip().lower().startswith(("socks5://", "socks5h://")):
            return value.strip()
    return None


def auto_detected_socks_proxy_urls(env: Mapping[str, str] | None = None) -> list[str]:
    source = env or os.environ
    if source.get("MEMORY_SYNC_DISABLE_LOCAL_PROXY_AUTODETECT") == "1":
        return []
    if has_configured_proxy_env(source):
        return []
    proxies: list[str] = []
    for candidate in DEFAULT_LOCAL_SOCKS_PROXIES:
        if supports_socks5_no_auth(candidate):
            proxies.append(candidate)
    return proxies


def socks_proxy_url(env: Mapping[str, str] | None = None) -> str | None:
    explicit = explicit_socks_proxy_url(env)
    if explicit:
        return explicit
    proxies = auto_detected_socks_proxy_urls(env)
    return proxies[0] if proxies else None


def available_socks_proxy_urls(env: Mapping[str, str] | None = None) -> list[str]:
    explicit = explicit_socks_proxy_url(env)
    if explicit:
        return [explicit]
    return auto_detected_socks_proxy_urls(env)


def git_ssh_command_for_proxy(proxy_url: str) -> str | None:
    if not SOCKS_PROXY_COMMAND.is_file():
        return None
    python_bin = shutil.which("python3") or shutil.which("python") or sys.executable
    proxy_command = shlex.join([python_bin, str(SOCKS_PROXY_COMMAND), "--proxy", proxy_url, "%h", "%p"])
    return shlex.join(["ssh", "-o", f"ProxyCommand={proxy_command}"])


def git_runtime_env(
    env: dict[str, str] | None = None,
    *,
    include_ssh_proxy_command: bool = True,
) -> dict[str, str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)

    proxy_url = explicit_socks_proxy_url(merged)
    if proxy_url:
        merged.setdefault("ALL_PROXY", proxy_url)
        merged.setdefault("all_proxy", proxy_url)
    if not include_ssh_proxy_command:
        merged.pop("GIT_SSH_COMMAND", None)

    return merged


def run_git(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    include_ssh_proxy_command: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run_command(
        ["git", *args],
        cwd=cwd,
        env=git_runtime_env(env, include_ssh_proxy_command=include_ssh_proxy_command),
        capture_output=True,
        check=check,
    )


def command_output(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or completed.stdout or "").strip()


def git_output(args: list[str], *, cwd: Path) -> str:
    return run_git(args, cwd=cwd).stdout.strip()


def git_success(args: list[str], *, cwd: Path) -> bool:
    return run_git(args, cwd=cwd, check=False).returncode == 0


def is_git_repo(root: Path) -> bool:
    return git_success(["rev-parse", "--is-inside-work-tree"], cwd=root)


def git_dir(root: Path) -> Path:
    raw = git_output(["rev-parse", "--git-dir"], cwd=root)
    git_path = Path(raw)
    if git_path.is_absolute():
        return git_path
    return (root / git_path).resolve()


def current_branch(root: Path) -> str:
    completed = run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=root, check=False)
    branch = completed.stdout.strip()
    if completed.returncode != 0 or not branch:
        raise MemoryRuntimeError(
            what=f"Memory repo `{root}` is not on a local branch.",
            why="Sync operations need a named branch to fetch, rebase, and push safely.",
            fix="Check out a branch in the memory repo before running `pre-read` or `post-write`.",
        )
    return branch


def upstream_ref(root: Path) -> str | None:
    completed = run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=root,
        check=False,
    )
    value = completed.stdout.strip()
    return value or None


def configured_remotes(root: Path) -> list[str]:
    output = run_git(["remote"], cwd=root, check=False).stdout.strip()
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def preferred_remote(root: Path) -> str | None:
    remotes = configured_remotes(root)
    if "origin" in remotes:
        return "origin"
    if len(remotes) == 1:
        return remotes[0]
    return None


def git_config_value(root: Path, key: str) -> str | None:
    completed = run_git(["config", "--get", key], cwd=root, check=False)
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        return None
    return value


def remote_url(root: Path, remote: str) -> str | None:
    return git_config_value(root, f"remote.{remote}.url")


def remote_push_url(root: Path, remote: str) -> str | None:
    return git_config_value(root, f"remote.{remote}.pushurl") or remote_url(root, remote)


def split_git_remote_url(remote_url: str) -> tuple[str, str] | None:
    value = remote_url.strip()
    if not value:
        return None
    if "://" in value:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").strip().lower()
        path = parsed.path.lstrip("/")
        if host and path:
            return host, path
        return None
    if ":" in value and "@" in value.split(":", 1)[0]:
        user_host, path = value.split(":", 1)
        if "@" not in user_host:
            return None
        _user, host = user_host.rsplit("@", 1)
        host = host.strip().lower()
        path = path.lstrip("/")
        if host and path:
            return host, path
    return None


def github_https_url(remote_url: str) -> str | None:
    parsed = split_git_remote_url(remote_url)
    if not parsed:
        return None
    host, repo_path = parsed
    if host not in GITHUB_REMOTE_HOSTS:
        return None
    return f"https://github.com/{repo_path}"


def github_token(env: Mapping[str, str] | None = None) -> tuple[str | None, str | None]:
    source = env or os.environ
    for name in GITHUB_TOKEN_ENV_VARS:
        value = source.get(name)
        if value and value.strip():
            return value.strip(), name
    return None, None


def github_http_extra_header(token: str) -> str:
    payload = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    return f"Authorization: Basic {payload}"


def is_auth_remote_failure(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in AUTH_REMOTE_ERROR_MARKERS)


def is_github_ssh_remote(remote_url: str) -> bool:
    parsed = split_git_remote_url(remote_url)
    if not parsed:
        return False
    host, _repo_path = parsed
    if host not in GITHUB_REMOTE_HOSTS:
        return False
    lowered = remote_url.strip().lower()
    return not lowered.startswith(("http://", "https://"))


def proxy_env_overrides(proxy_url: str, *, include_ssh_command: bool) -> tuple[tuple[str, str], ...]:
    env: list[tuple[str, str]] = [("ALL_PROXY", proxy_url), ("all_proxy", proxy_url)]
    if include_ssh_command:
        ssh_command = git_ssh_command_for_proxy(proxy_url)
        if ssh_command is None:
            return ()
        env.append(("GIT_SSH_COMMAND", ssh_command))
    return tuple(env)


def remote_execution_plans(
    root: Path,
    remote: str,
    *,
    push: bool,
    env: Mapping[str, str] | None = None,
) -> list[RemoteExecutionPlan]:
    source_url = remote_push_url(root, remote) if push else remote_url(root, remote)
    if not source_url:
        return [RemoteExecutionPlan(label=f"configured remote `{remote}`")]

    source_env = env or os.environ
    https_url = github_https_url(source_url)
    token, token_name = github_token(source_env)

    plans = [RemoteExecutionPlan(label=f"configured remote `{remote}`")]
    if is_github_ssh_remote(source_url):
        for proxy_url in available_socks_proxy_urls(source_env):
            env_overrides = proxy_env_overrides(proxy_url, include_ssh_command=True)
            if not env_overrides:
                continue
            plans.append(
                RemoteExecutionPlan(
                    label=f"GitHub SSH via SOCKS proxy {proxy_url}",
                    env_overrides=env_overrides,
                    notes=(f"SOCKS proxy: {proxy_url}",),
                )
            )

    if not https_url:
        return plans

    prefix: list[str] = []
    notes: list[str] = [f"GitHub HTTPS target: {https_url}"]
    if source_url != https_url:
        prefix.extend(["-c", f"remote.{remote}.url={https_url}"])
        notes.append("Transport override: alternate remote URL -> HTTPS")
    if push and source_url != https_url:
        prefix.extend(["-c", f"remote.{remote}.pushurl={https_url}"])
    if token:
        prefix.extend(["-c", f"http.extraHeader={github_http_extra_header(token)}"])
        notes.append(f"Authentication source: ${token_name}")
    else:
        notes.append("Authentication source: none")

    if prefix or source_url != https_url:
        plans.append(
            RemoteExecutionPlan(
                label="GitHub HTTPS fallback",
                prefix_args=tuple(prefix),
                notes=tuple(notes),
                include_ssh_proxy_command=False,
            )
        )

        if explicit_socks_proxy_url(source_env) is None:
            for proxy_url in available_socks_proxy_urls(source_env):
                plans.append(
                    RemoteExecutionPlan(
                        label=f"GitHub HTTPS via SOCKS proxy {proxy_url}",
                        prefix_args=tuple(prefix),
                        env_overrides=proxy_env_overrides(proxy_url, include_ssh_command=False),
                        notes=tuple([*notes, f"SOCKS proxy: {proxy_url}"]),
                    )
                )
    return plans


def remote_failure_fix(root: Path, remote: str, *, push: bool, output: str) -> str:
    source_url = remote_push_url(root, remote) if push else remote_url(root, remote)
    https_url = github_https_url(source_url or "")
    token, token_name = github_token()
    if not https_url:
        return "Check network access, remote reachability, and credentials, then retry the sync command."

    if token:
        return (
            f"GitHub HTTPS is reachable, but the configured token from `{token_name}` could not complete the "
            f"{'push' if push else 'fetch'}. Verify that the token still has access to `{https_url}`, or "
            "configure a git credential helper."
        )

    if is_auth_remote_failure(output):
        return (
            "The runtime exhausted GitHub SSH attempts and the HTTPS fallback reached GitHub but "
            "did not have credentials for the private repo. Export one of "
            f"{', '.join(f'`{name}`' for name in GITHUB_TOKEN_ENV_VARS)} or configure a git credential helper, "
            "then retry."
        )

    if is_github_ssh_remote(source_url or ""):
        return (
            "The runtime could not reach GitHub over direct SSH, any available local SOCKS-assisted SSH path, "
            "or HTTPS fallback. Check GitHub SSH reachability, export `MEMORY_SYNC_SOCKS_PROXY` if you know a "
            "working proxy, or export one of "
            f"{', '.join(f'`{name}`' for name in GITHUB_TOKEN_ENV_VARS)} so HTTPS fallback can authenticate."
        )

    return "The configured GitHub remote could not be reached. Check network access, proxy settings, and credentials, then retry."


def has_unresolved_conflicts(root: Path) -> bool:
    output = run_git(["diff", "--name-only", "--diff-filter=U"], cwd=root, check=False).stdout.strip()
    return bool(output)


def worktree_dirty(root: Path) -> bool:
    output = run_git(["status", "--porcelain"], cwd=root, check=False).stdout.strip()
    return bool(output)


def staged_changes(root: Path) -> bool:
    return run_git(["diff", "--cached", "--quiet"], cwd=root, check=False).returncode != 0


def repo_has_commits(root: Path) -> bool:
    return run_git(["rev-parse", "--verify", "HEAD"], cwd=root, check=False).returncode == 0


def validate_memory_repo(root: Path) -> None:
    if not root.exists():
        raise MemoryRuntimeError(
            what=f"Memory root `{root}` does not exist.",
            why="The runtime cannot read or sync a repo that is missing from disk.",
            fix="Run `init-memory --memory-root <path>` to create it or point the command at an existing repo.",
        )
    if not root.is_dir():
        raise MemoryRuntimeError(
            what=f"Memory root `{root}` is not a directory.",
            why="Memory commands operate on a directory-backed repo layout.",
            fix="Pass a directory path with `--memory-root` or re-run `init-memory` with a valid directory target.",
        )

    validate_memory_tree(root)

    if not is_git_repo(root):
        raise MemoryRuntimeError(
            what=f"Memory root `{root}` is not a git repo.",
            why="Sync behavior depends on git metadata for branches, remotes, and locking.",
            fix="Re-run `init-memory --memory-root <path>` to initialize git or adopt a valid git-backed memory repo.",
        )

    if has_unresolved_conflicts(root):
        raise MemoryRuntimeError(
            what=f"Memory repo `{root}` has unresolved conflicts.",
            why="Syncing on top of conflict markers can corrupt or hide memory updates.",
            fix="Resolve the conflicts in the memory repo, then retry the command.",
        )

    current_branch(root)


def copy_template_tree(root: Path) -> None:
    for template_path in TEMPLATE_ROOT.rglob("*"):
        if template_path.is_dir():
            continue
        relative = template_path.relative_to(TEMPLATE_ROOT)
        destination = root / relative
        ensure_parent(destination)
        shutil.copyfile(template_path, destination)


def initialize_git_repo(root: Path, branch: str) -> None:
    init_result = run_git(["init", "--initial-branch", branch], cwd=root, check=False)
    if init_result.returncode != 0:
        run_git(["init"], cwd=root)
        run_git(["symbolic-ref", "HEAD", f"refs/heads/{branch}"], cwd=root)


def configure_remote(root: Path, remote_url: str) -> None:
    existing = configured_remotes(root)
    if "origin" in existing:
        raise MemoryRuntimeError(
            what=f"Memory repo `{root}` already has an `origin` remote.",
            why="Initialization cannot safely overwrite an existing remote definition.",
            fix="Remove or rename the current remote, or use `--adopt` to bind the existing repo instead.",
        )
    run_git(["remote", "add", "origin", remote_url], cwd=root)


def bootstrap_commit_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "memory-skill bootstrap",
            "GIT_AUTHOR_EMAIL": "memory-skill@local.invalid",
            "GIT_COMMITTER_NAME": "memory-skill bootstrap",
            "GIT_COMMITTER_EMAIL": "memory-skill@local.invalid",
        }
    )
    return env


def create_bootstrap_commit(root: Path) -> None:
    run_git(["add", "-A"], cwd=root)
    completed = run_git(
        ["commit", "-m", "chore(memory): initialize memory repo"],
        cwd=root,
        env=bootstrap_commit_env(),
        check=False,
    )
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "").strip()
        raise MemoryRuntimeError(
            what=f"Bootstrapping the initial memory commit failed in `{root}`.",
            why="A fresh memory repo needs a clean initial commit so later sync commands can run immediately.",
            fix="Check git availability and retry `init-memory`; if the repo already exists, remove it or choose a different target directory.",
            details=[output] if output else [],
        )


def initialize_memory_repo(root: Path, branch: str, remote_url: str | None) -> None:
    if root.exists() and any(root.iterdir()):
        raise MemoryRuntimeError(
            what=f"Target directory `{root}` is not empty.",
            why="Initialization only creates new memory repos in empty directories to avoid overwriting existing files.",
            fix="Choose an empty directory or use `init-memory --adopt --memory-root <path>` for an existing repo.",
        )

    root.mkdir(parents=True, exist_ok=True)
    copy_template_tree(root)
    initialize_git_repo(root, branch)
    if remote_url:
        configure_remote(root, remote_url)
    create_bootstrap_commit(root)
    save_active_root(root)
    remote_line = f"Configured remote: {remote_url}" if remote_url else "Configured remote: local-only"
    print_success(
        "memory repo initialized",
        [
            f"Active root: {root}",
            f"Branch: {branch}",
            remote_line,
            f"State file: {STATE_FILE}",
        ],
    )


def adopt_memory_repo(root: Path) -> None:
    validate_memory_repo(root)
    save_active_root(root)
    print_success(
        "memory repo adopted",
        [
            f"Active root: {root}",
            f"State file: {STATE_FILE}",
        ],
    )


def file_age_seconds(path: Path) -> float:
    return time.time() - path.stat().st_mtime


def pid_is_alive(pid: int) -> bool | None:
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


class RepoLock:
    def __init__(self, root: Path, operation: str, timeout_seconds: float) -> None:
        self.root = root
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        self.git_dir = git_dir(root)
        self.lock_dir = self.git_dir / "memory-sync.lock"
        self.owner_file = self.lock_dir / "owner.json"
        self.heartbeat_file = self.lock_dir / "heartbeat"
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self.host_identity = detect_host_identity()
        self.hostname = self.host_identity.normalized

    def owner_payload(self) -> dict[str, Any]:
        return {
            "host": self.hostname,
            "raw_host": self.host_identity.raw,
            "host_source": self.host_identity.source,
            "pid": os.getpid(),
            "operation": self.operation,
            "memory_root": str(self.root),
            "started_at": iso_now(),
        }

    def write_owner(self) -> None:
        self.lock_dir.mkdir()
        write_json(self.owner_file, self.owner_payload())
        self.touch_heartbeat()

    def touch_heartbeat(self) -> None:
        ensure_parent(self.heartbeat_file)
        self.heartbeat_file.write_text(f"{time.time():.6f}\n", encoding="utf-8")

    def read_owner(self) -> dict[str, Any]:
        try:
            return read_json(self.owner_file)
        except FileNotFoundError:
            return {}
        except MemoryRuntimeError:
            return {}

    def heartbeat_age(self) -> float | None:
        try:
            return file_age_seconds(self.heartbeat_file)
        except FileNotFoundError:
            return None

    def stale(self) -> tuple[bool, list[str]]:
        details: list[str] = []
        age = self.heartbeat_age()
        if age is None:
            return True, ["Lock heartbeat file is missing."]
        details.append(f"Heartbeat age: {age:.1f}s")
        if age <= STALE_AFTER_SECONDS:
            return False, details

        owner = self.read_owner()
        owner_host = owner.get("host")
        owner_pid = int(owner.get("pid", 0) or 0)
        if same_machine_hostname(owner_host, self.hostname) or same_machine_hostname(owner.get("raw_host"), self.hostname):
            alive = pid_is_alive(owner_pid)
            details.append(f"Owner pid alive: {alive}")
            if alive:
                return False, details
        return True, details

    def remove(self) -> None:
        shutil.rmtree(self.lock_dir, ignore_errors=True)

    def heartbeat_loop(self) -> None:
        while not self._stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            with contextlib.suppress(OSError):
                self.touch_heartbeat()

    def start_heartbeat(self) -> None:
        self._heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._stop_event.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=HEARTBEAT_INTERVAL_SECONDS * 2)

    def describe_owner(self) -> list[str]:
        owner = self.read_owner()
        lines = []
        if owner:
            for key in ("host", "raw_host", "host_source", "pid", "operation", "memory_root", "started_at"):
                value = owner.get(key)
                if value is not None:
                    lines.append(f"{key}={value}")
        age = self.heartbeat_age()
        if age is not None:
            lines.append(f"heartbeat_age={age:.1f}s")
        return lines

    def acquire(self) -> None:
        deadline = time.time() + self.timeout_seconds
        while True:
            try:
                self.write_owner()
                self.start_heartbeat()
                return
            except FileExistsError:
                is_stale, details = self.stale()
                if is_stale:
                    self.remove()
                    continue
                if time.time() >= deadline:
                    raise MemoryRuntimeError(
                        what=f"Timed out waiting for the sync lock in `{self.lock_dir}`.",
                        why="Only one memory sync operation can modify a repo clone at a time.",
                        fix="Wait for the active sync to finish, or inspect the owner details and terminate the stuck process if needed.",
                        details=self.describe_owner() + details,
                    )
                time.sleep(WAIT_POLL_SECONDS)

    def release(self) -> None:
        self.stop_heartbeat()
        self.remove()

    def __enter__(self) -> "RepoLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()


def is_transient_remote_failure(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in TRANSIENT_REMOTE_ERROR_MARKERS)


def run_git_remote_with_retry(
    args: list[str],
    *,
    cwd: Path,
    remote: str | None = None,
    push: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    plans = [RemoteExecutionPlan(label="configured remote")]
    if remote:
        plans = remote_execution_plans(cwd, remote, push=push)

    attempt_details: list[str] = []
    completed: subprocess.CompletedProcess[str] | None = None
    for plan in plans:
        if plan.notes:
            attempt_details.extend(f"{plan.label}: {note}" for note in plan.notes)
        for attempt in range(1, REMOTE_RETRY_ATTEMPTS + 1):
            plan_env = dict(plan.env_overrides) if plan.env_overrides else None
            completed = run_git(
                [*plan.prefix_args, *args],
                cwd=cwd,
                env=plan_env,
                include_ssh_proxy_command=plan.include_ssh_proxy_command,
                check=False,
            )
            if completed.returncode == 0:
                return completed, attempt_details

            output = command_output(completed)
            detail = output or f"git {' '.join(args)} exited with code {completed.returncode}."
            attempt_details.append(f"{plan.label} attempt {attempt}/{REMOTE_RETRY_ATTEMPTS}: {detail}")
            if attempt >= REMOTE_RETRY_ATTEMPTS or not is_transient_remote_failure(output):
                break
            time.sleep(REMOTE_RETRY_BASE_DELAY_SECONDS * attempt)

    assert completed is not None
    return completed, attempt_details


def fetch_remote(root: Path, remote: str) -> None:
    completed, attempts = run_git_remote_with_retry(["fetch", "--quiet", remote], cwd=root, remote=remote)
    if completed.returncode != 0:
        raise MemoryRuntimeError(
            what=f"Fetching from `{remote}` failed for `{root}`.",
            why="The memory repo could not refresh remote state before syncing.",
            fix=remote_failure_fix(root, remote, push=False, output=command_output(completed)),
            details=attempts or [command_output(completed)],
        )


def fast_forward(root: Path, upstream: str) -> None:
    completed = run_git(["merge", "--ff-only", "--quiet", upstream], cwd=root, check=False)
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "").strip()
        raise MemoryRuntimeError(
            what=f"Fast-forward to `{upstream}` failed for `{root}`.",
            why="The local memory repo has diverged from its upstream and cannot be refreshed safely.",
            fix="Reconcile the repo manually, then retry `pre-read`.",
            details=[output] if output else [],
        )


def rebase_onto(root: Path, upstream: str) -> None:
    completed = run_git(["rebase", "--quiet", upstream], cwd=root, check=False)
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "").strip()
        raise MemoryRuntimeError(
            what=f"Rebase onto `{upstream}` failed for `{root}`.",
            why="The memory repo cannot safely publish local changes until the upstream state is reconciled.",
            fix="Resolve the rebase in the memory repo or abort it, then retry `post-write`.",
            details=[output] if output else [],
        )


def push_branch(root: Path, remote: str, branch: str, set_upstream: bool = False) -> None:
    args = ["push", "--quiet"]
    if set_upstream:
        args.append("-u")
    args.extend([remote, f"HEAD:{branch}"])
    completed, attempts = run_git_remote_with_retry(args, cwd=root, remote=remote, push=True)
    if completed.returncode != 0:
        raise MemoryRuntimeError(
            what=f"Pushing branch `{branch}` to `{remote}` failed for `{root}`.",
            why="The runtime could not publish memory updates to the configured remote.",
            fix=remote_failure_fix(root, remote, push=True, output=command_output(completed)),
            details=attempts or [command_output(completed)],
        )


def create_commit(root: Path, message: str) -> bool:
    run_git(["add", "-A"], cwd=root)
    if not staged_changes(root):
        return False
    completed = run_git(["commit", "-m", message], cwd=root, check=False)
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "").strip()
        raise MemoryRuntimeError(
            what=f"Committing memory changes failed in `{root}`.",
            why="`post-write` must create a local commit before it can sync or preserve changes safely.",
            fix="Ensure git user.name and user.email are configured and resolve any commit blockers, then retry `post-write`.",
            details=[output] if output else [],
        )
    return True


def sync_pre_read(root: Path, timeout_seconds: float) -> None:
    validate_memory_repo(root)
    if worktree_dirty(root):
        raise MemoryRuntimeError(
            what=f"Memory repo `{root}` has uncommitted changes.",
            why="`pre-read` only operates on a clean repo so it can trust the synchronized snapshot.",
            fix="Commit or discard the local changes, or run `post-write` first if they should be published.",
        )

    with RepoLock(root, "pre-read", timeout_seconds):
        upstream = upstream_ref(root)
        if not upstream:
            remote = preferred_remote(root)
            if remote:
                print_success(
                    "pre-read complete",
                    [
                        f"Memory root: {root}",
                        f"Result: clean local repo; remote `{remote}` is configured but no upstream tracking branch exists yet.",
                    ],
                )
            else:
                print_success(
                    "pre-read complete",
                    [
                        f"Memory root: {root}",
                        "Result: clean local-only repo; no upstream fetch was required.",
                    ],
                )
            return

        remote = upstream.split("/", 1)[0]
        fetch_remote(root, remote)
        fast_forward(root, upstream)
        revision = git_output(["rev-parse", "--short", "HEAD"], cwd=root) if repo_has_commits(root) else "no-commits"
        print_success(
            "pre-read complete",
            [
                f"Memory root: {root}",
                f"Upstream: {upstream}",
                f"Revision: {revision}",
            ],
        )


def sync_post_write(root: Path, message: str, timeout_seconds: float) -> None:
    validate_memory_repo(root)

    with RepoLock(root, "post-write", timeout_seconds):
        created_commit = create_commit(root, message)
        upstream = upstream_ref(root)

        if upstream:
            remote = upstream.split("/", 1)[0]
            fetch_remote(root, remote)
            rebase_onto(root, upstream)
            branch = current_branch(root)
            push_branch(root, remote, branch)
            revision = git_output(["rev-parse", "--short", "HEAD"], cwd=root)
            print_success(
                "post-write complete",
                [
                    f"Memory root: {root}",
                    f"Commit created: {created_commit}",
                    f"Upstream: {upstream}",
                    f"Revision: {revision}",
                ],
            )
            return

        remote = preferred_remote(root)
        branch = current_branch(root)
        if remote and repo_has_commits(root):
            push_branch(root, remote, branch, set_upstream=True)
            revision = git_output(["rev-parse", "--short", "HEAD"], cwd=root)
            print_success(
                "post-write complete",
                [
                    f"Memory root: {root}",
                    f"Commit created: {created_commit}",
                    f"Remote bootstrap: branch `{branch}` now tracks `{remote}/{branch}`.",
                    f"Revision: {revision}",
                ],
            )
            return

        revision = git_output(["rev-parse", "--short", "HEAD"], cwd=root) if repo_has_commits(root) else "no-commits"
        print_success(
            "post-write complete",
            [
                f"Memory root: {root}",
                f"Commit created: {created_commit}",
                "Result: local-only repo; no upstream push was required.",
                f"Revision: {revision}",
            ],
        )


def build_parser() -> argparse.ArgumentParser:
    parser = FriendlyArgumentParser(
        prog="memory-runtime",
        description="Cross-platform runtime for memory-skill bootstrap and sync commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=FriendlyArgumentParser)

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize or adopt a memory repo and save it as the active root.",
    )
    init_parser.add_argument("--memory-root", help="Target memory repo path.")
    init_parser.add_argument("--remote", help="Optional remote URL to configure as origin.")
    init_parser.add_argument("--branch", default="main", help="Branch name for new repos. Default: main.")
    init_parser.add_argument(
        "--adopt",
        action="store_true",
        help="Adopt an existing valid memory repo instead of creating a new one.",
    )

    sync_parser = subparsers.add_parser(
        "sync",
        help="Run memory sync operations against the active memory repo.",
    )
    sync_parser.add_argument("operation", choices=["pre-read", "post-write"])
    sync_parser.add_argument("--memory-root", help="Explicit memory repo path.")
    sync_parser.add_argument(
        "-m",
        "--message",
        default=DEFAULT_COMMIT_MESSAGE,
        help=f"Commit message for post-write. Default: {DEFAULT_COMMIT_MESSAGE!r}.",
    )
    sync_parser.add_argument(
        "--lock-timeout-seconds",
        type=float,
        default=WAIT_TIMEOUT_SECONDS,
        help=f"Lock wait timeout in seconds. Default: {WAIT_TIMEOUT_SECONDS}.",
    )

    machine_parser = subparsers.add_parser(
        "machine",
        help="Resolve the current machine hostname for memory routing.",
    )
    machine_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the resolved hostname as JSON instead of the normalized hostname only.",
    )

    return parser


def handle_init(args: argparse.Namespace) -> None:
    root, source = resolve_memory_root(args.memory_root)
    if args.adopt:
        adopt_memory_repo(root)
        return

    if root.exists() and any(root.iterdir()):
        raise MemoryRuntimeError(
            what=f"Target directory `{root}` already contains files.",
            why="Creating a new memory repo in a non-empty directory risks overwriting unrelated data.",
            fix="Choose an empty directory, or re-run the command with `--adopt` if this is already a valid memory repo.",
            details=[f"Resolved from: {source}"],
        )

    initialize_memory_repo(root, args.branch, args.remote)


def handle_sync(args: argparse.Namespace) -> None:
    root, _source = resolve_memory_root(args.memory_root)
    if args.operation == "pre-read":
        sync_pre_read(root, args.lock_timeout_seconds)
        return
    sync_post_write(root, args.message, args.lock_timeout_seconds)


def handle_machine(args: argparse.Namespace) -> None:
    identity = detect_host_identity()
    if args.json:
        print(
            json.dumps(
                {
                    "raw_hostname": identity.raw,
                    "normalized_hostname": identity.normalized,
                    "source": identity.source,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    print(identity.normalized)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        handle_init(args)
    elif args.command == "sync":
        handle_sync(args)
    elif args.command == "machine":
        handle_machine(args)
    else:
        parser.error(f"unknown command: {args.command}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MemoryRuntimeError as error:
        print_failure(error)
        raise SystemExit(error.exit_code)
