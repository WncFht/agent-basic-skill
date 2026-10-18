"""Verify native backend selection without loading speech models."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/transcribe.py"
spec = importlib.util.spec_from_file_location("asr_transcribe", SCRIPT)
transcribe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transcribe)


class BackendSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patcher = patch.object(transcribe, "SKILL_ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def bundle(self, platform):
        directory = self.root / "bin" / f"parakeet-v0.5.0-bin-{platform}"
        directory.mkdir(parents=True)
        (directory / "parakeet-cli").touch()
        return directory

    def test_macos_auto_falls_back_when_only_linux_binary_exists(self):
        self.bundle("linux-cuda-x64")
        gguf = self.root / "weights.gguf"
        gguf.touch()
        with (
            patch.object(transcribe.sys, "platform", "darwin"),
            patch.object(transcribe, "_has_accel", return_value=True),
        ):
            directory = transcribe._default_bin_dir()
            self.assertFalse((directory / "parakeet-cli").exists())
            self.assertEqual(
                transcribe.resolve_backend("en", "auto", directory, gguf, self.root),
                "sherpa",
            )

    def test_each_platform_selects_its_own_installed_bundle(self):
        mac = self.bundle("macos-metal-arm64")
        linux = self.bundle("linux-cuda-x64")
        for platform, expected in [("darwin", mac), ("linux", linux)]:
            with (
                self.subTest(platform=platform),
                patch.object(transcribe.sys, "platform", platform),
            ):
                self.assertEqual(transcribe._default_bin_dir(), expected)

    def test_linux_does_not_select_a_macos_only_bundle(self):
        self.bundle("macos-metal-arm64")
        with patch.object(transcribe.sys, "platform", "linux"):
            self.assertFalse((transcribe._default_bin_dir() / "parakeet-cli").exists())


if __name__ == "__main__":
    unittest.main()
