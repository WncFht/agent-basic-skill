import json
import shutil
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
AGENT_INSTALL_DOC = REPO_ROOT / ".codex" / "INSTALL.md"
EXPECTED_SKILLS = {
    "pdf": [
        "SKILL.md",
        "agents/openai.yaml",
        "assets/pdf.png",
        "LICENSE.txt",
    ],
    "report-download": [
        "SKILL.md",
        "agents/openai.yaml",
        "pyproject.toml",
        "scripts/download_report.py",
        "scripts/search_and_download_report.py",
        "uv.lock",
    ],
    "git-commit": [
        "SKILL.md",
    ],
    "jujutsu": [
        "SKILL.md",
        "LICENSE.txt",
    ],
    "jupyter-notebook": [
        "SKILL.md",
        "LICENSE.txt",
        "agents/openai.yaml",
        "assets/experiment-template.ipynb",
        "assets/jupyter-small.svg",
        "assets/jupyter.png",
        "assets/tutorial-template.ipynb",
        "references/experiment-patterns.md",
        "references/notebook-structure.md",
        "references/quality-checklist.md",
        "references/tutorial-patterns.md",
        "scripts/new_notebook.py",
    ],
    "deepresearch-skill": [
        "SKILL.md",
        "agents/openai.yaml",
        "assets/report-template.tex",
        "references/multimodal-ingestion.md",
    ],
    "frontend-slides": [
        "SKILL.md",
        "LICENSE",
        "MEMORY.md",
        "README.md",
        "STYLE_PRESETS.md",
        "animation-patterns.md",
        "html-template.md",
        "scripts/extract-pptx.py",
        "viewport-base.css",
    ],
    "bilinote-video-note": [
        "SKILL.md",
        "scripts/resolve_bilinote_paths.py",
    ],
    "paperflow-pipeline-notes": [
        "SKILL.md",
        "scripts/resolve_paperflow_paths.py",
    ],
    "shuiyuan-cache-skill": [
        "SKILL.md",
        "external-repos.json",
        "scripts/resolve_shuiyuan_paths.py",
        "references/output_schema.md",
        "references/runbook.md",
        "references/runtime_layout.md",
        "references/topic-study-workflow.md",
        "references/troubleshooting.md",
    ],
    "bilibili-up-digest": [
        "SKILL.md",
        "external-repos.json",
        "scripts/resolve_pulsedeck_repo.py",
        "references/templates.md",
    ],
    "video-note-render-pdf-v0": [
        "SKILL.md",
        "agents/openai.yaml",
        "assets/case-manifest.template.json",
        "assets/notes-template.tex",
        "external-repos.json",
        "scripts/resolve_video_note_paths.py",
        "references/adapter-contract.md",
        "references/case-bundle-contract.md",
        "references/figure-delivery-guidance.md",
        "references/mode-routing.md",
        "references/platform-notes.md",
        "references/runbook.md",
        "references/troubleshooting.md",
    ],
    "video-note-render-pdf-v1": [
        "SKILL.md",
        "agents/openai.yaml",
        "assets/case-manifest.template.json",
        "assets/notes-template.tex",
        "external-repos.json",
        "scripts/resolve_video_note_paths.py",
        "references/adapter-contract.md",
        "references/case-bundle-contract.md",
        "references/coverage-and-revision-guidance.md",
        "references/figure-delivery-guidance.md",
        "references/mode-routing.md",
        "references/platform-notes.md",
        "references/runbook.md",
        "references/troubleshooting.md",
    ],
}
WRAPPER_SKILLS = {
    "bilinote-video-note",
    "paperflow-pipeline-notes",
    "shuiyuan-cache-skill",
    "bilibili-up-digest",
    "video-note-render-pdf-v0",
    "video-note-render-pdf-v1",
}
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
