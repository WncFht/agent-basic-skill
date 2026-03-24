import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "bundle-manifest.json"
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_bundle.py"
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
}


class BundleStructureTests(unittest.TestCase):
    def load_manifest(self) -> dict:
        with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_manifest_describes_all_expected_skills(self) -> None:
        manifest = self.load_manifest()
        skill_names = {item["name"] for item in manifest["skills"]}
        self.assertEqual(skill_names, set(EXPECTED_SKILLS))

    def test_manifest_required_files_exist_in_repo(self) -> None:
        manifest = self.load_manifest()
        for item in manifest["skills"]:
            skill_dir = REPO_ROOT / item["path"]
            self.assertTrue(skill_dir.is_dir(), msg=f"missing skill dir {skill_dir}")
            for relative_path in item["required_files"]:
                self.assertTrue(
                    (skill_dir / relative_path).exists(),
                    msg=f"missing {item['name']} companion file: {relative_path}",
                )


class InstallScriptTests(unittest.TestCase):
    def run_install(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(INSTALL_SCRIPT), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_single_skill_install_preserves_companion_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = self.run_install("--skill", "jupyter-notebook", "--dest", tmp_dir)
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            installed_root = Path(tmp_dir) / "jupyter-notebook"
            for relative_path in EXPECTED_SKILLS["jupyter-notebook"]:
                self.assertTrue(
                    (installed_root / relative_path).exists(),
                    msg=f"missing installed jupyter-notebook file: {relative_path}",
                )

    def test_bundle_install_installs_every_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = self.run_install("--all", "--dest", tmp_dir)
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            for skill_name, required_files in EXPECTED_SKILLS.items():
                installed_root = Path(tmp_dir) / skill_name
                self.assertTrue(installed_root.is_dir(), msg=f"missing installed skill {skill_name}")
                for relative_path in required_files:
                    self.assertTrue(
                        (installed_root / relative_path).exists(),
                        msg=f"missing installed {skill_name} file: {relative_path}",
                    )


if __name__ == "__main__":
    unittest.main()
