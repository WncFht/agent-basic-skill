from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "runtime" / "memory_runtime.py"
RUNTIME_SPEC = importlib.util.spec_from_file_location("memory_runtime", RUNTIME_PATH)
assert RUNTIME_SPEC is not None and RUNTIME_SPEC.loader is not None
memory_runtime = importlib.util.module_from_spec(RUNTIME_SPEC)
sys.modules[RUNTIME_SPEC.name] = memory_runtime
RUNTIME_SPEC.loader.exec_module(memory_runtime)
SYNC_WRAPPER = ROOT / "scripts" / "sync-memory.sh"
INIT_WRAPPER = ROOT / "scripts" / "init-memory.sh"
MACHINE_WRAPPER = ROOT / "scripts" / "resolve-machine.sh"
SYNC_CMD = ROOT / "scripts" / "sync-memory.cmd"
INIT_CMD = ROOT / "scripts" / "init-memory.cmd"
MACHINE_CMD = ROOT / "scripts" / "resolve-machine.cmd"
SYNC_PS1 = ROOT / "scripts" / "sync-memory.ps1"
INIT_PS1 = ROOT / "scripts" / "init-memory.ps1"
MACHINE_PS1 = ROOT / "scripts" / "resolve-machine.ps1"


def run(args: list[str], *, env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


class MemoryRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.home_dir = self.temp_dir / "home"
        self.home_dir.mkdir()
        run(["git", "config", "--global", "user.name", "memory-skill test"], env=self.env())
        run(["git", "config", "--global", "user.email", "memory-skill@example.invalid"], env=self.env())

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def env(self, **overrides: str) -> dict[str, str]:
        env = os.environ.copy()
        env["HOME"] = str(self.home_dir)
        env["USERPROFILE"] = str(self.home_dir)
        env.update(overrides)
        return env

    def init_repo(self, path: Path, *, remote: Path | None = None) -> subprocess.CompletedProcess[str]:
        args = [str(INIT_WRAPPER), "--memory-root", str(path)]
        if remote:
            args.extend(["--remote", str(remote)])
        return run(args, env=self.env())

    def sync(self, path: Path, operation: str, *, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = self.env(**(env_overrides or {}))
        return run([str(SYNC_WRAPPER), "--memory-root", str(path), operation], env=env)

    def test_init_creates_memory_repo_and_state(self) -> None:
        memory_root = self.temp_dir / "memory"
        result = self.init_repo(memory_root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((memory_root / "core.md").is_file())
        self.assertTrue((memory_root / "rules.md").is_file())
        self.assertTrue((memory_root / "machines" / "index.md").is_file())
        self.assertTrue((memory_root / "repos" / "index.md").is_file())
        state_file = self.home_dir / ".codex" / "state" / "memory-skill" / "state.json"
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["memory_root"], str(memory_root))
        self.assertIn("memory repo initialized", result.stdout)

    def test_explicit_memory_root_overrides_env_and_state(self) -> None:
        state_root = self.temp_dir / "state-root"
        env_root = self.temp_dir / "env-root"
        explicit_root = self.temp_dir / "explicit-root"

        self.assertEqual(self.init_repo(state_root).returncode, 0)
        self.assertEqual(self.init_repo(env_root).returncode, 0)
        self.assertEqual(self.init_repo(explicit_root).returncode, 0)

        state_file = self.home_dir / ".codex" / "state" / "memory-skill" / "state.json"
        state_file.write_text(
            json.dumps({"memory_root": str(state_root)}, indent=2) + "\n",
            encoding="utf-8",
        )

        result = run(
            [str(SYNC_WRAPPER), "--memory-root", str(explicit_root), "pre-read"],
            env=self.env(MEMORY_ROOT=str(env_root)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(explicit_root), result.stdout)
        self.assertNotIn(str(state_root), result.stdout)

    def test_saved_root_is_used_when_no_override_exists(self) -> None:
        memory_root = self.temp_dir / "memory"
        self.assertEqual(self.init_repo(memory_root).returncode, 0)
        result = run([str(SYNC_WRAPPER), "pre-read"], env=self.env())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(memory_root), result.stdout)

    def test_adopt_rejects_invalid_existing_directory(self) -> None:
        invalid_root = self.temp_dir / "not-a-memory-repo"
        invalid_root.mkdir()
        (invalid_root / "random.txt").write_text("hello\n", encoding="utf-8")
        result = run(
            [str(INIT_WRAPPER), "--memory-root", str(invalid_root), "--adopt"],
            env=self.env(),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("What happened:", result.stderr)
        self.assertIn("not a valid memory repo layout", result.stderr)

    def test_pre_read_rejects_dirty_worktree(self) -> None:
        memory_root = self.temp_dir / "memory"
        self.assertEqual(self.init_repo(memory_root).returncode, 0)
        (memory_root / "core.md").write_text("dirty\n", encoding="utf-8")
        result = self.sync(memory_root, "pre-read")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uncommitted changes", result.stderr)

    def test_post_write_bootstraps_remote_tracking(self) -> None:
        remote = self.temp_dir / "remote.git"
        git(["init", "--bare", str(remote)], cwd=self.temp_dir)
        memory_root = self.temp_dir / "memory"
        init_result = self.init_repo(memory_root, remote=remote)
        self.assertEqual(init_result.returncode, 0, init_result.stderr)

        with (memory_root / "core.md").open("a", encoding="utf-8") as handle:
            handle.write("new line\n")

        result = self.sync(memory_root, "post-write")
        self.assertEqual(result.returncode, 0, result.stderr)
        upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=memory_root)
        self.assertEqual(upstream.stdout.strip(), "origin/main")
        self.assertIn("Remote bootstrap", result.stdout)

    def test_stale_lock_is_recovered(self) -> None:
        memory_root = self.temp_dir / "memory"
        self.assertEqual(self.init_repo(memory_root).returncode, 0)
        git_dir = Path(git(["rev-parse", "--git-dir"], cwd=memory_root).stdout.strip())
        if not git_dir.is_absolute():
            git_dir = memory_root / git_dir
        lock_dir = git_dir / "memory-sync.lock"
        lock_dir.mkdir()
        (lock_dir / "owner.json").write_text(
            json.dumps({"host": "localhost", "pid": 999999, "operation": "pre-read"}),
            encoding="utf-8",
        )
        heartbeat = lock_dir / "heartbeat"
        heartbeat.write_text("0\n", encoding="utf-8")
        stale_time = time.time() - 120
        os.utime(heartbeat, (stale_time, stale_time))

        result = self.sync(memory_root, "pre-read")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(lock_dir.exists())

    def test_live_lock_times_out_with_owner_details(self) -> None:
        memory_root = self.temp_dir / "memory"
        self.assertEqual(self.init_repo(memory_root).returncode, 0)
        git_dir = Path(git(["rev-parse", "--git-dir"], cwd=memory_root).stdout.strip())
        if not git_dir.is_absolute():
            git_dir = memory_root / git_dir
        lock_dir = git_dir / "memory-sync.lock"
        lock_dir.mkdir()
        (lock_dir / "owner.json").write_text(
            json.dumps(
                {
                    "host": socket.gethostname(),
                    "pid": os.getpid(),
                    "operation": "pre-read",
                    "memory_root": str(memory_root),
                    "started_at": "now",
                }
            ),
            encoding="utf-8",
        )
        (lock_dir / "heartbeat").write_text("0\n", encoding="utf-8")

        result = self.sync(
            memory_root,
            "pre-read",
            env_overrides={
                "MEMORY_SYNC_WAIT_TIMEOUT_SECONDS": "0.4",
                "MEMORY_SYNC_WAIT_POLL_SECONDS": "0.1",
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Timed out waiting for the sync lock", result.stderr)
        self.assertIn("host=", result.stderr)
        self.assertIn("pid=", result.stderr)

    def test_supported_entrypoints_exist_and_posix_wrappers_work(self) -> None:
        self.assertTrue(SYNC_WRAPPER.is_file())
        self.assertTrue(INIT_WRAPPER.is_file())
        self.assertTrue(MACHINE_WRAPPER.is_file())
        self.assertTrue(SYNC_CMD.is_file())
        self.assertTrue(INIT_CMD.is_file())
        self.assertTrue(MACHINE_CMD.is_file())
        self.assertTrue(SYNC_PS1.is_file())
        self.assertTrue(INIT_PS1.is_file())
        self.assertTrue(MACHINE_PS1.is_file())

        init_help = run([str(INIT_WRAPPER), "--help"], env=self.env())
        sync_help = run([str(SYNC_WRAPPER), "--help"], env=self.env())
        machine_help = run([str(MACHINE_WRAPPER), "--help"], env=self.env())
        self.assertEqual(init_help.returncode, 0, init_help.stderr)
        self.assertEqual(sync_help.returncode, 0, sync_help.stderr)
        self.assertEqual(machine_help.returncode, 0, machine_help.stderr)
        self.assertIn("usage:", init_help.stdout)
        self.assertIn("usage:", sync_help.stdout)
        self.assertIn("usage:", machine_help.stdout)

    def test_normalize_machine_hostname_strips_local_suffix_and_normalizes_case(self) -> None:
        self.assertEqual(
            memory_runtime.normalize_machine_hostname("Fanghaotians-MacBook-Air.local"),
            "fanghaotians-macbook-air",
        )

    def test_detect_host_identity_falls_back_to_environment(self) -> None:
        with (
            mock.patch.object(memory_runtime.socket, "gethostname", side_effect=OSError("boom")),
            mock.patch.object(memory_runtime.platform, "node", return_value=""),
            mock.patch.object(memory_runtime.os, "uname", side_effect=OSError("boom"), create=True),
        ):
            identity = memory_runtime.detect_host_identity({"HOSTNAME": "ArchBox.local"})

        self.assertEqual(identity.raw, "ArchBox.local")
        self.assertEqual(identity.normalized, "archbox")
        self.assertEqual(identity.source, "HOSTNAME")

    def test_resolve_machine_wrapper_outputs_normalized_hostname_by_default(self) -> None:
        result = run([str(MACHINE_WRAPPER)], env=self.env())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout.strip(), r"^[a-z0-9-]+$")

    def test_resolve_machine_wrapper_outputs_json(self) -> None:
        result = run([str(MACHINE_WRAPPER), "--json"], env=self.env())
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("normalized_hostname", payload)
        self.assertIn("raw_hostname", payload)
        self.assertIn("source", payload)

    def test_github_https_url_parses_common_remote_forms(self) -> None:
        self.assertEqual(
            memory_runtime.github_https_url("git@github.com:example-org/agent-memory.git"),
            "https://github.com/example-org/agent-memory.git",
        )
        self.assertEqual(
            memory_runtime.github_https_url("ssh://git@ssh.github.com:443/example-org/agent-memory.git"),
            "https://github.com/example-org/agent-memory.git",
        )
        self.assertEqual(
            memory_runtime.github_https_url("https://github.com/example-org/agent-memory.git"),
            "https://github.com/example-org/agent-memory.git",
        )
        self.assertIsNone(memory_runtime.github_https_url("git@gitlab.com:org/repo.git"))

    def test_github_token_prefers_memory_specific_env(self) -> None:
        token, source = memory_runtime.github_token(
            {
                "GITHUB_TOKEN": "global-token",
                "MEMORY_SYNC_GITHUB_TOKEN": "memory-token",
            }
        )
        self.assertEqual(token, "memory-token")
        self.assertEqual(source, "MEMORY_SYNC_GITHUB_TOKEN")

    def test_socks_proxy_url_prefers_explicit_env(self) -> None:
        proxy = memory_runtime.socks_proxy_url({"MEMORY_SYNC_SOCKS_PROXY": "socks5://127.0.0.1:7897"})
        self.assertEqual(proxy, "socks5://127.0.0.1:7897")

    def test_git_runtime_env_preserves_explicit_proxy_without_forcing_git_ssh_command(self) -> None:
        env = memory_runtime.git_runtime_env({"MEMORY_SYNC_SOCKS_PROXY": "socks5://127.0.0.1:7897"})
        self.assertEqual(env["ALL_PROXY"], "socks5://127.0.0.1:7897")
        self.assertEqual(env["all_proxy"], "socks5://127.0.0.1:7897")
        self.assertNotIn("GIT_SSH_COMMAND", env)

    def test_remote_execution_plans_try_direct_then_proxy_ssh_then_https(self) -> None:
        memory_root = self.temp_dir / "memory"
        self.assertEqual(self.init_repo(memory_root).returncode, 0)
        git(["remote", "add", "origin", "git@github.com:example-org/agent-memory.git"], cwd=memory_root)

        plans = memory_runtime.remote_execution_plans(
            memory_root,
            "origin",
            push=False,
            env={"MEMORY_SYNC_SOCKS_PROXY": "socks5://127.0.0.1:7897"},
        )

        self.assertEqual(
            [plan.label for plan in plans],
            [
                "configured remote `origin`",
                "GitHub SSH via SOCKS proxy socks5://127.0.0.1:7897",
                "GitHub HTTPS fallback",
            ],
        )
        self.assertIn(("ALL_PROXY", "socks5://127.0.0.1:7897"), plans[1].env_overrides)
        self.assertIn(("GIT_SSH_COMMAND", memory_runtime.git_ssh_command_for_proxy("socks5://127.0.0.1:7897")), plans[1].env_overrides)

    def test_remote_execution_plans_include_auto_detected_https_proxy_fallbacks(self) -> None:
        memory_root = self.temp_dir / "memory"
        self.assertEqual(self.init_repo(memory_root).returncode, 0)
        git(["remote", "add", "origin", "git@github.com:example-org/agent-memory.git"], cwd=memory_root)

        with mock.patch.object(
            memory_runtime,
            "auto_detected_socks_proxy_urls",
            return_value=["socks5://127.0.0.1:7897", "socks5h://127.0.0.1:7891"],
        ):
            plans = memory_runtime.remote_execution_plans(memory_root, "origin", push=False, env={})

        self.assertEqual(
            [plan.label for plan in plans],
            [
                "configured remote `origin`",
                "GitHub SSH via SOCKS proxy socks5://127.0.0.1:7897",
                "GitHub SSH via SOCKS proxy socks5h://127.0.0.1:7891",
                "GitHub HTTPS fallback",
                "GitHub HTTPS via SOCKS proxy socks5://127.0.0.1:7897",
                "GitHub HTTPS via SOCKS proxy socks5h://127.0.0.1:7891",
            ],
        )

    def test_remote_execution_plans_still_add_proxy_retries_when_git_ssh_command_is_present(self) -> None:
        memory_root = self.temp_dir / "memory"
        self.assertEqual(self.init_repo(memory_root).returncode, 0)
        git(["remote", "add", "origin", "git@github.com:example-org/agent-memory.git"], cwd=memory_root)

        plans = memory_runtime.remote_execution_plans(
            memory_root,
            "origin",
            push=False,
            env={
                "GIT_SSH_COMMAND": "/bin/false",
                "MEMORY_SYNC_SOCKS_PROXY": "socks5://127.0.0.1:7897",
            },
        )

        self.assertEqual(plans[1].label, "GitHub SSH via SOCKS proxy socks5://127.0.0.1:7897")
        self.assertIn(("GIT_SSH_COMMAND", memory_runtime.git_ssh_command_for_proxy("socks5://127.0.0.1:7897")), plans[1].env_overrides)

    def test_git_runtime_env_omits_git_ssh_command_when_disabled(self) -> None:
        env = memory_runtime.git_runtime_env(
            {"MEMORY_SYNC_SOCKS_PROXY": "socks5://127.0.0.1:7897"},
            include_ssh_proxy_command=False,
        )
        self.assertEqual(env["ALL_PROXY"], "socks5://127.0.0.1:7897")

    def test_git_runtime_env_does_not_force_socks_for_http_proxy_port(self) -> None:
        ready = threading.Event()
        stop = threading.Event()
        server_errors: list[Exception] = []

        def fake_http_proxy() -> None:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    server.bind(("127.0.0.1", 0))
                    server.listen()
                    port = server.getsockname()[1]
                    self.http_proxy_port = port
                    ready.set()
                    server.settimeout(0.2)
                    while not stop.is_set():
                        try:
                            conn, _addr = server.accept()
                        except socket.timeout:
                            continue
                        with conn:
                            with contextlib.suppress(OSError):
                                conn.recv(1024)
                                conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            except Exception as exc:  # pragma: no cover - test infrastructure
                server_errors.append(exc)
                ready.set()

        self.http_proxy_port = 0
        thread = threading.Thread(target=fake_http_proxy, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=3), "proxy test server did not start")
        self.addCleanup(stop.set)
        self.addCleanup(thread.join, 1)
        if server_errors:
            raise server_errors[0]

        http_proxy = f"http://127.0.0.1:{self.http_proxy_port}"
        candidate = f"socks5://127.0.0.1:{self.http_proxy_port}"
        with mock.patch.object(memory_runtime, "DEFAULT_LOCAL_SOCKS_PROXIES", (candidate,)):
            env = memory_runtime.git_runtime_env(
                {
                    "ALL_PROXY": http_proxy,
                    "all_proxy": http_proxy,
                    "HTTP_PROXY": http_proxy,
                    "HTTPS_PROXY": http_proxy,
                }
            )

        self.assertEqual(env["ALL_PROXY"], http_proxy)
        self.assertEqual(env["all_proxy"], http_proxy)
        self.assertNotIn("GIT_SSH_COMMAND", env)

    def test_socks_proxy_url_accepts_auto_detected_proxy_after_handshake(self) -> None:
        ready = threading.Event()
        stop = threading.Event()
        server_errors: list[Exception] = []

        def fake_socks_proxy() -> None:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    server.bind(("127.0.0.1", 0))
                    server.listen()
                    port = server.getsockname()[1]
                    self.socks_proxy_port = port
                    ready.set()
                    server.settimeout(0.2)
                    while not stop.is_set():
                        try:
                            conn, _addr = server.accept()
                        except socket.timeout:
                            continue
                        with conn:
                            greeting = conn.recv(3)
                            if greeting == b"\x05\x01\x00":
                                conn.sendall(b"\x05\x00")
            except Exception as exc:  # pragma: no cover - test infrastructure
                server_errors.append(exc)
                ready.set()

        self.socks_proxy_port = 0
        thread = threading.Thread(target=fake_socks_proxy, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=3), "proxy test server did not start")
        self.addCleanup(stop.set)
        self.addCleanup(thread.join, 1)
        if server_errors:
            raise server_errors[0]

        candidate = f"socks5://127.0.0.1:{self.socks_proxy_port}"
        with mock.patch.object(memory_runtime, "DEFAULT_LOCAL_SOCKS_PROXIES", (candidate,)):
            proxy = memory_runtime.socks_proxy_url({})

        self.assertEqual(proxy, candidate)

    def test_git_runtime_env_skips_auto_detect_when_http_proxy_env_is_already_set(self) -> None:
        ready = threading.Event()
        stop = threading.Event()
        server_errors: list[Exception] = []

        def fake_socks_proxy() -> None:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    server.bind(("127.0.0.1", 0))
                    server.listen()
                    port = server.getsockname()[1]
                    self.preconfigured_proxy_port = port
                    ready.set()
                    server.settimeout(0.2)
                    while not stop.is_set():
                        try:
                            conn, _addr = server.accept()
                        except socket.timeout:
                            continue
                        with conn:
                            greeting = conn.recv(3)
                            if greeting == b"\x05\x01\x00":
                                conn.sendall(b"\x05\x00")
            except Exception as exc:  # pragma: no cover - test infrastructure
                server_errors.append(exc)
                ready.set()

        self.preconfigured_proxy_port = 0
        thread = threading.Thread(target=fake_socks_proxy, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(timeout=3), "proxy test server did not start")
        self.addCleanup(stop.set)
        self.addCleanup(thread.join, 1)
        if server_errors:
            raise server_errors[0]

        http_proxy = "http://127.0.0.1:7897"
        candidate = f"socks5://127.0.0.1:{self.preconfigured_proxy_port}"
        with mock.patch.object(memory_runtime, "DEFAULT_LOCAL_SOCKS_PROXIES", (candidate,)):
            env = memory_runtime.git_runtime_env(
                {
                    "ALL_PROXY": http_proxy,
                    "all_proxy": http_proxy,
                    "HTTP_PROXY": http_proxy,
                    "HTTPS_PROXY": http_proxy,
                }
            )

        self.assertEqual(env["ALL_PROXY"], http_proxy)
        self.assertNotIn("GIT_SSH_COMMAND", env)

    def test_fetch_remote_tries_github_https_fallback_after_ssh_failure(self) -> None:
        calls: list[list[str]] = []
        ssh_failure = subprocess.CompletedProcess(
            ["git", "fetch", "--quiet", "origin"],
            128,
            "",
            "Connection closed by 20.27.177.118 port 443",
        )
        https_success = subprocess.CompletedProcess(
            ["git", "fetch", "--quiet", "origin"],
            0,
            "",
            "",
        )

        def fake_run_git(
            args: list[str],
            *,
            cwd: Path,
            env: dict[str, str] | None = None,
            include_ssh_proxy_command: bool = True,
            check: bool = True,
        ) -> subprocess.CompletedProcess[str]:
            calls.append([*args, f"include_ssh_proxy_command={include_ssh_proxy_command}"])
            if args == ["fetch", "--quiet", "origin"]:
                return ssh_failure
            if args[-3:] == ["fetch", "--quiet", "origin"] and any(
                part == "remote.origin.url=https://github.com/example-org/agent-memory.git" for part in args
            ):
                return https_success
            raise AssertionError(f"Unexpected git args: {args}")

        with (
            mock.patch.object(
                memory_runtime,
                "remote_execution_plans",
                return_value=[
                    memory_runtime.RemoteExecutionPlan(label="configured remote `origin`"),
                    memory_runtime.RemoteExecutionPlan(
                        label="GitHub HTTPS fallback",
                        prefix_args=(
                            "-c",
                            "remote.origin.url=https://github.com/example-org/agent-memory.git",
                            "-c",
                            "http.extraHeader=Authorization: Basic dGVzdA==",
                        ),
                        include_ssh_proxy_command=False,
                    ),
                ],
            ),
            mock.patch.object(memory_runtime, "run_git", side_effect=fake_run_git),
        ):
            completed, details = memory_runtime.run_git_remote_with_retry(
                ["fetch", "--quiet", "origin"],
                cwd=self.temp_dir,
                remote="origin",
            )

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(any(args[:-1] == ["fetch", "--quiet", "origin"] for args in calls))
        self.assertTrue(
            any(
                args[-4:-1] == ["fetch", "--quiet", "origin"]
                and "remote.origin.url=https://github.com/example-org/agent-memory.git" in args
                for args in calls
            )
        )
        self.assertTrue(any(args[-1] == "include_ssh_proxy_command=False" for args in calls if "remote.origin.url=https://github.com/example-org/agent-memory.git" in args))
        self.assertTrue(any("configured remote `origin` attempt 1/3" in detail for detail in details))

    def test_run_git_remote_with_retry_applies_plan_env_overrides(self) -> None:
        calls: list[tuple[list[str], dict[str, str] | None]] = []
        ssh_failure = subprocess.CompletedProcess(
            ["git", "fetch", "--quiet", "origin"],
            128,
            "",
            "Connection closed by 20.27.177.118 port 443",
        )
        proxy_success = subprocess.CompletedProcess(
            ["git", "fetch", "--quiet", "origin"],
            0,
            "",
            "",
        )

        def fake_run_git(
            args: list[str],
            *,
            cwd: Path,
            env: dict[str, str] | None = None,
            include_ssh_proxy_command: bool = True,
            check: bool = True,
        ) -> subprocess.CompletedProcess[str]:
            calls.append((args, env))
            if env is None:
                return ssh_failure
            if env.get("GIT_SSH_COMMAND") == "ssh-proxy":
                return proxy_success
            raise AssertionError(f"Unexpected git call: args={args}, env={env}")

        with (
            mock.patch.object(
                memory_runtime,
                "remote_execution_plans",
                return_value=[
                    memory_runtime.RemoteExecutionPlan(label="configured remote `origin`"),
                    memory_runtime.RemoteExecutionPlan(
                        label="GitHub SSH via SOCKS proxy socks5://127.0.0.1:7897",
                        env_overrides=(
                            ("ALL_PROXY", "socks5://127.0.0.1:7897"),
                            ("all_proxy", "socks5://127.0.0.1:7897"),
                            ("GIT_SSH_COMMAND", "ssh-proxy"),
                        ),
                    ),
                ],
            ),
            mock.patch.object(memory_runtime, "run_git", side_effect=fake_run_git),
            mock.patch.object(memory_runtime, "REMOTE_RETRY_ATTEMPTS", 1),
        ):
            completed, _details = memory_runtime.run_git_remote_with_retry(
                ["fetch", "--quiet", "origin"],
                cwd=self.temp_dir,
                remote="origin",
            )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(calls[0][1], None)
        self.assertEqual(calls[1][1]["GIT_SSH_COMMAND"], "ssh-proxy")

    def test_fetch_remote_surfaces_github_token_fix_after_https_auth_failure(self) -> None:
        memory_root = self.temp_dir / "memory"
        self.assertEqual(self.init_repo(memory_root).returncode, 0)
        git(["remote", "add", "origin", "git@github.com:example-org/agent-memory.git"], cwd=memory_root)

        ssh_failure = subprocess.CompletedProcess(
            ["git", "fetch", "--quiet", "origin"],
            128,
            "",
            "Connection closed by 20.27.177.118 port 443",
        )
        https_auth_failure = subprocess.CompletedProcess(
            ["git", "fetch", "--quiet", "origin"],
            128,
            "",
            "HTTP/2 401 Unauthorized\nfatal: could not read Username for 'https://github.com': No such device or address",
        )

        def fake_run_git(
            args: list[str],
            *,
            cwd: Path,
            env: dict[str, str] | None = None,
            include_ssh_proxy_command: bool = True,
            check: bool = True,
        ) -> subprocess.CompletedProcess[str]:
            if args[:3] == ["config", "--get", "remote.origin.url"]:
                return subprocess.CompletedProcess(["git", *args], 0, "git@github.com:example-org/agent-memory.git\n", "")
            if args == ["fetch", "--quiet", "origin"]:
                return ssh_failure
            if args[-3:] == ["fetch", "--quiet", "origin"] and any(
                part == "remote.origin.url=https://github.com/example-org/agent-memory.git" for part in args
            ):
                return https_auth_failure
            raise AssertionError(f"Unexpected git args: {args}")

        with mock.patch.object(memory_runtime, "run_git", side_effect=fake_run_git):
            with self.assertRaises(memory_runtime.MemoryRuntimeError) as context:
                memory_runtime.fetch_remote(memory_root, "origin")

        self.assertIn("MEMORY_SYNC_GITHUB_TOKEN", context.exception.fix)
        self.assertTrue(any("GitHub HTTPS fallback" in detail for detail in context.exception.details))


if __name__ == "__main__":
    unittest.main()
