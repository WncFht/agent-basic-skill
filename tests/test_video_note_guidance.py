import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VIDEO_NOTE_ROOT = REPO_ROOT / "skills" / "video-note-render-pdf"


class VideoNoteGuidanceTests(unittest.TestCase):
    def test_default_prompt_preserves_quality_signals(self) -> None:
        content = (VIDEO_NOTE_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("official cover image", content)
        self.assertIn("exhaustive frame recall", content)
        self.assertIn("final synthesis chapter", content)
        self.assertIn("filter greetings, sponsorship, channel logistics", content)
        self.assertIn("prefer official subtitles over cookies-based subtitles over ASR fallback", content)

    def test_skill_doc_includes_content_rules_and_delivery(self) -> None:
        content = (VIDEO_NOTE_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Teaching Content Rules", content)
        self.assertIn("greetings", content)
        self.assertIn("channel logistics", content)
        self.assertIn("## 交付物", content)
        self.assertIn("speaker closing discussion", content)
        self.assertIn("references/platform-notes.md", content)
        self.assertIn("references/figure-delivery-guidance.md", content)

    def test_platform_notes_capture_bilibili_caveats(self) -> None:
        content = (VIDEO_NOTE_ROOT / "references" / "platform-notes.md").read_text(encoding="utf-8")
        self.assertIn("分 P", content)
        self.assertIn("b23.tv", content)
        self.assertIn("danmaku", content)
        self.assertIn("visual-only", content)

    def test_figure_delivery_guidance_exists(self) -> None:
        content = (VIDEO_NOTE_ROOT / "references" / "figure-delivery-guidance.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("高召回选帧规则", content)
        self.assertIn("contact sheet", content)
        self.assertIn("总结与延伸", content)
        self.assertIn("note.pdf", content)

    def test_case_manifest_tracks_auditable_guidance_fields(self) -> None:
        payload = json.loads(
            (VIDEO_NOTE_ROOT / "assets" / "case-manifest.template.json").read_text(encoding="utf-8")
        )
        runtime = payload["runtime"]
        self.assertIn("part_selection", runtime)
        self.assertIn("subtitle_language", runtime)
        self.assertIn("subtitle_kind", runtime)
        self.assertIn("visual_only_reason", runtime)
        artifacts = payload["artifacts"]
        self.assertEqual(artifacts["cover_image"], "cover.png")
        self.assertEqual(artifacts["figures_dir"], "figures")
        self.assertEqual(artifacts["pdf_preview_dir"], "pdf_preview")


if __name__ == "__main__":
    unittest.main()
