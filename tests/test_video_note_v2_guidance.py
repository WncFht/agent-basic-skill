import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VIDEO_NOTE_V2_ROOT = REPO_ROOT / "skills" / "video-note-render-pdf-v2"


class VideoNoteV2GuidanceTests(unittest.TestCase):
    def test_default_prompt_mentions_new_v2_controls(self) -> None:
        content = (VIDEO_NOTE_V2_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("subtitle-char guardrail", content)
        self.assertIn("carrier family plus support profile plus recall budget", content)
        self.assertIn("visual obligation ledger", content)
        self.assertIn("revision actions", content)

    def test_skill_doc_mentions_length_routing_and_revision_contract(self) -> None:
        content = (VIDEO_NOTE_V2_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Length Guardrail", content)
        self.assertIn("carrier family + support profile + recall budget", content)
        self.assertIn("visual_obligation_ledger.json", content)
        self.assertIn("revision-actions.json", content)
        self.assertIn("宁可略长，不要明显偏短", content)

    def test_mode_routing_explains_each_axis_in_chinese(self) -> None:
        content = (VIDEO_NOTE_V2_ROOT / "references" / "mode-routing.md").read_text(encoding="utf-8")
        self.assertIn("document-led", content)
        self.assertIn("slide-lecture", content)
        self.assertIn("evidence-led", content)
        self.assertIn("anchor-dense", content)
        self.assertIn("中文解释", content)
        self.assertIn("Recall budget", content)

    def test_coverage_guidance_contains_piecewise_guardrail(self) -> None:
        content = (VIDEO_NOTE_V2_ROOT / "references" / "coverage-and-revision-guidance.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("0.55S", content)
        self.assertIn("0.18S", content)
        self.assertIn("min_note_chars", content)
        self.assertIn("soft_note_char_range", content)
        self.assertIn("review/revision-actions.json", content)

    def test_case_manifest_tracks_routing_and_visual_obligation_fields(self) -> None:
        payload = json.loads(
            (VIDEO_NOTE_V2_ROOT / "assets" / "case-manifest.template.json").read_text(encoding="utf-8")
        )
        self.assertIn("routing", payload)
        self.assertIn("length_budget", payload)
        self.assertEqual(payload["artifacts"]["visual_obligation_ledger"], "work/visual_obligation_ledger.json")
        self.assertEqual(payload["artifacts"]["revision_actions"], "review/revision-actions.json")


if __name__ == "__main__":
    unittest.main()
