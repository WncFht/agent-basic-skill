"""Regression checks for diagnostics that must affect health-check exit codes."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class HealthCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.work = self.home / "work"
        self.work.mkdir()
        shared = self.home / ".agents"
        (shared / "skills").mkdir(parents=True)
        (shared / "AGENTS.md").write_text("instructions\n")
        for link, target in [
            ("AGENTS.md", ".agents/AGENTS.md"),
            (".claude/AGENTS.md", "../.agents/AGENTS.md"),
            (".claude/skills", "../.agents/skills"),
            (".codex/AGENTS.md", "../.agents/AGENTS.md"),
            (".kimi-code/AGENTS.md", "../.agents/AGENTS.md"),
        ]:
            path = self.home / link
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)
        (self.home / ".claude/settings.json").write_text(
            json.dumps(
                {
                    "pluginConfigs": {
                        "agents-md@builtin": {
                            "options": {"instructionFiles": "claude-md-and-agents-md"}
                        }
                    }
                }
            )
        )

    def run_doctor(self, *repos):
        return subprocess.run(
            ["bash", str(SCRIPTS / "skill_doctor.sh"), *map(str, repos)],
            cwd=self.work,
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True,
            text=True,
            check=False,
        )

    def add_skill(self, folder, text):
        path = self.home / ".agents" / folder / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(text)

    def test_name_mismatch_fails_in_summary_and_exit_code(self):
        self.add_skill("skills/probe", "---\nname: other\ndescription: probe\n---\n")
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn("1 FAIL", result.stdout)
        self.assertNotIn("name 与目录名一致", result.stdout)

    def test_body_name_does_not_replace_missing_frontmatter_name(self):
        self.add_skill("skills/probe", "---\ndescription: probe\n---\nname: probe\n")
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn("frontmatter 无 name", result.stdout)

    def test_incubator_mismatch_warns_without_failing(self):
        self.add_skill("incubator/probe", "---\nname: other\ndescription: probe\n---\n")
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0)
        self.assertIn("1 WARN, 0 FAIL", result.stdout)

    def test_dangling_instruction_links_fail(self):
        (self.home / ".agents/AGENTS.md").unlink()
        result = self.run_doctor()
        self.assertEqual(result.returncode, 1)
        self.assertIn("断链", result.stdout)

    def test_repo_skills_link_must_point_to_repo_skills(self):
        repo = self.home / "repo"
        (repo / ".agents/skills").mkdir(parents=True)
        (repo / ".claude").mkdir()
        (repo / ".claude/skills").symlink_to(self.home / ".agents/skills")
        result = self.run_doctor(repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("1 FAIL", result.stdout)

    def test_malformed_dependency_manifest_fails(self):
        path = self.home / ".agents/skills/probe/deps.toml"
        path.parent.mkdir(parents=True)
        path.write_text("[[dep]\n")
        result = subprocess.run(
            ["python3", str(SCRIPTS / "skill_deps.py"), "--quiet"],
            cwd=self.work,
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("读取或解析失败", result.stderr)


if __name__ == "__main__":
    unittest.main()
