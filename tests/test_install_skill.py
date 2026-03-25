import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_INSTALLER = REPO_ROOT / "scripts" / "install_skill.py"


def run_installer(script: Path, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(script), "demo-wrapper", "--json"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=merged_env,
    )


def run_installer_for_skill(
    script: Path,
    cwd: Path,
    skill_name: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(script), skill_name, "--json"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=merged_env,
    )


def init_git_repo(path: Path, tracked_files: dict[str, str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.name", "Codex Tests"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "codex-tests@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    for relative_path, content in tracked_files.items():
        target = path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


class InstallSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.root = Path(self.tmp_dir.name)
        self.repo_root = self.root / "agent-basic-skill"
        (self.repo_root / "scripts").mkdir(parents=True)
        shutil.copy2(SOURCE_INSTALLER, self.repo_root / "scripts" / "install_skill.py")
        (self.repo_root / "skills" / "demo-wrapper").mkdir(parents=True)
        (self.repo_root / "skills" / "demo-wrapper" / "SKILL.md").write_text(
            textwrap.dedent(
                """\
                ---
                name: demo-wrapper
                description: demo
                ---

                # Demo
                """
            ),
            encoding="utf-8",
        )

    def write_manifest(self, clone_url: str, detect_paths: list[str], clone_dir: str) -> None:
        manifest = {
            "version": 1,
            "repositories": [
                {
                    "id": "repo:demo/tool",
                    "repo": "demo/tool",
                    "clone_url": clone_url,
                    "default_clone_dir": clone_dir,
                    "default_detect_paths": detect_paths,
                    "env_var": "DEMO_TOOL_REPO",
                    "override_key": "repo:demo/tool",
                    "markers": ["tool.txt"],
                }
            ],
        }
        (self.repo_root / "skills" / "demo-wrapper" / "external-repos.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_existing_repo_skips_clone(self) -> None:
        existing_repo = self.root / "Desktop" / "src" / "DemoTool"
        init_git_repo(existing_repo, {"tool.txt": "ok\n"})
        self.write_manifest(
            clone_url=str(self.root / "origin.git"),
            detect_paths=["~/Desktop/src/DemoTool"],
            clone_dir="~/Desktop/src/DemoTool",
        )

        result = run_installer(
            self.repo_root / "scripts" / "install_skill.py",
            self.repo_root,
            {"HOME": str(self.root), "CODEX_HOME": str(self.root / ".codex")},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        dependency = payload["results"][0]["dependencies"][0]
        self.assertEqual(dependency["status"], "already_present")
        self.assertEqual(dependency["resolution"], "default-detect")

    def test_missing_repo_clones_to_default_dir(self) -> None:
        origin_repo = self.root / "origin-tool"
        init_git_repo(origin_repo, {"tool.txt": "ok\n"})
        self.write_manifest(
            clone_url=str(origin_repo),
            detect_paths=["~/Desktop/src/DemoTool"],
            clone_dir="~/Desktop/src/DemoTool",
        )

        result = run_installer(
            self.repo_root / "scripts" / "install_skill.py",
            self.repo_root,
            {"HOME": str(self.root), "CODEX_HOME": str(self.root / ".codex")},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        dependency = payload["results"][0]["dependencies"][0]
        self.assertEqual(dependency["status"], "cloned")
        target_repo = self.root / "Desktop" / "src" / "DemoTool"
        self.assertTrue((target_repo / "tool.txt").exists())

    def test_invalid_existing_target_fails_without_overwrite(self) -> None:
        invalid_dir = self.root / "Desktop" / "src" / "DemoTool"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "not-a-repo.txt").write_text("keep me\n", encoding="utf-8")
        origin_repo = self.root / "origin-tool"
        init_git_repo(origin_repo, {"tool.txt": "ok\n"})
        self.write_manifest(
            clone_url=str(origin_repo),
            detect_paths=["~/Desktop/src/DemoTool"],
            clone_dir="~/Desktop/src/DemoTool",
        )

        result = run_installer(
            self.repo_root / "scripts" / "install_skill.py",
            self.repo_root,
            {"HOME": str(self.root), "CODEX_HOME": str(self.root / ".codex")},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((invalid_dir / "not-a-repo.txt").exists())

    def test_install_replaces_previous_copy_with_wrapper_contents(self) -> None:
        origin_repo = self.root / "origin-tool"
        init_git_repo(origin_repo, {"tool.txt": "ok\n"})
        self.write_manifest(
            clone_url=str(origin_repo),
            detect_paths=["~/Desktop/src/DemoTool"],
            clone_dir="~/Desktop/src/DemoTool",
        )
        dest_skill = self.root / ".codex" / "skills" / "demo-wrapper"
        dest_skill.mkdir(parents=True)
        (dest_skill / "old-heavy-file.txt").write_text("stale\n", encoding="utf-8")

        result = run_installer(
            self.repo_root / "scripts" / "install_skill.py",
            self.repo_root,
            {"HOME": str(self.root), "CODEX_HOME": str(self.root / ".codex")},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertFalse((dest_skill / "old-heavy-file.txt").exists())
        self.assertTrue((dest_skill / "SKILL.md").exists())
        self.assertTrue((dest_skill / "external-repos.json").exists())

    def test_real_video_note_skill_manifest_uses_env_repo(self) -> None:
        runtime_repo = self.root / "video-note-pipeline"
        runtime_repo.mkdir()
        (runtime_repo / "pyproject.toml").write_text("[project]\nname='video-note-pipeline'\n", encoding="utf-8")
        (runtime_repo / "README.md").write_text("# runtime\n", encoding="utf-8")

        result = run_installer_for_skill(
            SOURCE_INSTALLER,
            REPO_ROOT,
            "video-note-render-pdf",
            {
                "HOME": str(self.root),
                "CODEX_HOME": str(self.root / ".codex"),
                "VIDEO_NOTE_PIPELINE_REPO": str(runtime_repo),
            },
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        dependency = payload["results"][0]["dependencies"][0]
        self.assertEqual(dependency["repo"], "WncFht/video-note-pipeline")
        self.assertEqual(dependency["status"], "already_present")
        self.assertEqual(dependency["resolution"], "env:VIDEO_NOTE_PIPELINE_REPO")
        installed_root = self.root / ".codex" / "skills" / "video-note-render-pdf"
        self.assertTrue((installed_root / "SKILL.md").exists())
        self.assertTrue((installed_root / "external-repos.json").exists())


if __name__ == "__main__":
    unittest.main()
