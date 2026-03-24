import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_script(script: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=merged_env,
    )


class WrapperResolutionTests(unittest.TestCase):
    def test_bilinote_prefers_env_backend_root(self) -> None:
        script = REPO_ROOT / "skills" / "bilinote-video-note" / "scripts" / "resolve_bilinote_paths.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            backend_root = Path(tmp_dir) / "BiliNote" / "backend"
            backend_root.mkdir(parents=True)
            (backend_root / "pyproject.toml").write_text("[project]\nname='bilinote'\n", encoding="utf-8")
            result = run_script(script, env={"BILINOTE_BACKEND_ROOT": str(backend_root)})
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["backend_root"], str(backend_root.resolve()))
            self.assertEqual(payload["resolution"], "env:BILINOTE_BACKEND_ROOT")

    def test_paperflow_prefers_local_override(self) -> None:
        script = REPO_ROOT / "skills" / "paperflow-pipeline-notes" / "scripts" / "resolve_paperflow_paths.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            paperflow_repo = Path(tmp_dir) / "paperflow"
            notes_root = Path(tmp_dir) / "research-notes"
            paperflow_repo.mkdir()
            notes_root.mkdir()
            (paperflow_repo / "pyproject.toml").write_text("[project]\nname='paperflow'\n", encoding="utf-8")
            override_path = Path(tmp_dir) / "source-overrides.json"
            override_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "sources": {
                            "repo:WncFht/paperflow": str(paperflow_repo),
                            "workspace:research-notes": str(notes_root),
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = run_script(
                script,
                env={"AGENT_BASIC_SKILL_SOURCE_OVERRIDES": str(override_path)},
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["paperflow_repo"], str(paperflow_repo.resolve()))
            self.assertEqual(payload["research_notes_root"], str(notes_root.resolve()))
            self.assertEqual(payload["resolution"]["paperflow_repo"], "local-override")
            self.assertEqual(payload["resolution"]["research_notes_root"], "local-override")

    def test_shuiyuan_uses_default_candidate_and_runtime_default(self) -> None:
        script = REPO_ROOT / "skills" / "shuiyuan-cache-skill" / "scripts" / "resolve_shuiyuan_paths.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            home = Path(tmp_dir)
            repo_root = home / "Desktop" / "src" / "shuiyuan_exporter"
            repo_root.mkdir(parents=True)
            (repo_root / "pyproject.toml").write_text("[project]\nname='shuiyuan_exporter'\n", encoding="utf-8")
            result = run_script(script, env={"HOME": str(home)})
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["repo_root"], str(repo_root.resolve()))
            self.assertEqual(
                payload["cache_root"],
                str((home / ".local" / "share" / "shuiyuan-cache-skill").resolve()),
            )

    def test_pulsedeck_prefers_env_repo_root(self) -> None:
        script = REPO_ROOT / "skills" / "bilibili-up-digest" / "scripts" / "resolve_pulsedeck_repo.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            home = Path(tmp_dir)
            repo_root = home / "src" / "PulseDeck"
            repo_root.mkdir(parents=True)
            result = run_script(
                script,
                env={
                    "HOME": str(home),
                    "BILIBILI_UP_DIGEST_REPO": str(repo_root),
                },
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["repo_root"], str(repo_root.resolve()))
            self.assertEqual(
                payload["vault_root"],
                str((home / "Desktop" / "obsidian" / "bilibili").resolve()),
            )


if __name__ == "__main__":
    unittest.main()
