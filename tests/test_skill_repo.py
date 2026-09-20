import json
import shutil
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
AGENT_INSTALL_DOC = REPO_ROOT / ".codex" / "INSTALL.md"
EXPECTED_SKILLS = {
    "memory-skill": [
        "LICENSE", "README.md", "README.zh-CN.md", "SKILL.md",
        "docs/sync-and-troubleshooting.md",
        "runtime/memory_runtime.py", "runtime/ssh_via_socks.py",
        "scripts/init-memory.cmd", "scripts/init-memory.ps1", "scripts/init-memory.sh",
        "scripts/resolve-machine.cmd", "scripts/resolve-machine.ps1", "scripts/resolve-machine.sh",
        "scripts/sync-memory.cmd", "scripts/sync-memory.ps1", "scripts/sync-memory.sh",
        "templates/memory-tree/core.md", "templates/memory-tree/machines/index.md",
        "templates/memory-tree/repos/index.md", "templates/memory-tree/rules.md",
        "templates/memory-tree/topics/.gitkeep",
        "tests/test_memory_runtime.py",
    ],
    "paper-note-skill": [
        "SKILL.md",
        "references/annotation-rules.md", "references/latex-and-lint.md",
        "references/scripts-redesign.md", "references/section-guidance.md",
        "references/translation-format.md", "references/workflow.md",
        "scripts/assets/binhex.tex",
        "scripts/commands/__init__.py", "scripts/commands/build.py",
        "scripts/commands/config.py", "scripts/commands/doctor.py",
        "scripts/commands/fetch.py", "scripts/commands/lint.py",
        "scripts/commands/run.py", "scripts/commands/setup.py",
        "scripts/commands/visual_check.py",
        "scripts/core/__init__.py", "scripts/core/arxiv.py",
        "scripts/core/build_exec.py", "scripts/core/build_plan.py",
        "scripts/core/build_report.py", "scripts/core/doctor.py",
        "scripts/core/entry.py", "scripts/core/latex_compat.py",
        "scripts/core/lint_parse.py", "scripts/core/lint_rules.py",
        "scripts/core/models.py", "scripts/core/output.py",
        "scripts/core/source_clean.py", "scripts/core/user_config.py",
        "scripts/core/visual.py", "scripts/core/workspace.py",
        "scripts/docs/README.md", "scripts/docs/commands.md", "scripts/docs/core-modules.md",
        "scripts/paper_note.py",
    ],
    "plot-skill": [
        "SKILL.md", "agents/openai.yaml",
        "examples/bar-demo.png", "examples/donut-demo.png", "examples/line-demo.png",
        "examples/radar-demo.png", "examples/scatter-demo.png",
        "references/chart-families.md", "references/design-dimensions.md", "references/presets.md",
        "scripts/bar_demo.py", "scripts/donut_demo.py", "scripts/line_demo.py",
        "scripts/radar_demo.py", "scripts/render_all_examples.py", "scripts/scatter_demo.py",
        "scripts/style_presets.py",
    ],
    "report-download": [
        "SKILL.md", "agents/openai.yaml", "pyproject.toml",
        "scripts/download_report.py", "scripts/search_and_download_report.py", "uv.lock",
    ],
}
WRAPPER_SKILLS = set()
DISALLOWED_WRAPPER_NAMES = {
    "tests",
    "src",
    "cache",
    ".cache",
    "docs",
    "browser_profile",
    "node_modules",
}


class SkillRepoTests(unittest.TestCase):
    def test_agent_install_doc_exists(self) -> None:
        self.assertTrue(AGENT_INSTALL_DOC.exists(), msg="missing .codex/INSTALL.md")
        content = AGENT_INSTALL_DOC.read_text(encoding="utf-8")
        self.assertIn("~/.agents/skills", content)
        self.assertIn("git clone https://github.com/WncFht/agent-basic-skill.git", content)

    def test_repo_contains_expected_skill_dirs(self) -> None:
        skill_names = {path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()}
        self.assertEqual(skill_names, set(EXPECTED_SKILLS))

    def test_expected_companion_files_exist(self) -> None:
        for skill_name, required_files in EXPECTED_SKILLS.items():
            skill_dir = SKILLS_ROOT / skill_name
            self.assertTrue(skill_dir.is_dir(), msg=f"missing skill dir {skill_dir}")
            for relative_path in required_files:
                self.assertTrue(
                    (skill_dir / relative_path).exists(),
                    msg=f"missing {skill_name} companion file: {relative_path}",
                )

    def test_wrapper_skills_stay_thin(self) -> None:
        for skill_name in WRAPPER_SKILLS:
            skill_dir = SKILLS_ROOT / skill_name
            for entry in skill_dir.iterdir():
                self.assertNotIn(
                    entry.name,
                    DISALLOWED_WRAPPER_NAMES,
                    msg=f"wrapper skill contains disallowed entry {entry.name}: {skill_name}",
                )

    def test_direct_directory_copy_preserves_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            destination_root = Path(tmp_dir)
            for skill_name, required_files in EXPECTED_SKILLS.items():
                source_root = SKILLS_ROOT / skill_name
                target_root = destination_root / skill_name
                shutil.copytree(source_root, target_root)
                for relative_path in required_files:
                    self.assertTrue(
                        (target_root / relative_path).exists(),
                        msg=f"missing copied {skill_name} file: {relative_path}",
                    )

    def test_external_repo_manifests_include_required_fields(self) -> None:
        required_fields = {
            "id",
            "repo",
            "clone_url",
            "default_clone_dir",
            "default_detect_paths",
            "env_var",
            "override_key",
            "markers",
        }
        for skill_name in WRAPPER_SKILLS:
            manifest_path = SKILLS_ROOT / skill_name / "external-repos.json"
            if not manifest_path.exists():
                continue
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload.get("version"), 1, msg=f"invalid manifest version: {skill_name}")
            repositories = payload.get("repositories", [])
            self.assertTrue(repositories, msg=f"empty repositories list: {skill_name}")
            for repo_spec in repositories:
                self.assertTrue(
                    required_fields.issubset(repo_spec),
                    msg=f"missing required manifest fields in {skill_name}: {repo_spec}",
                )
                self.assertTrue(repo_spec["markers"], msg=f"empty markers in {skill_name}")


if __name__ == "__main__":
    unittest.main()
