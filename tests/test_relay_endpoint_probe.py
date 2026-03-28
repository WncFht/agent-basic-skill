import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "relay-endpoint-probe" / "scripts" / "probe_relay.py"
SPEC = importlib.util.spec_from_file_location("relay_endpoint_probe", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RelayEndpointProbeTests(unittest.TestCase):
    def test_base_normalization(self) -> None:
        self.assertEqual(MODULE.ensure_openai_base("https://example.com/codex"), "https://example.com/codex/v1")
        self.assertEqual(MODULE.ensure_openai_base("https://example.com/v1"), "https://example.com/v1")
        self.assertEqual(MODULE.ensure_anthropic_base("https://example.com/v1"), "https://example.com")
        self.assertEqual(MODULE.ensure_anthropic_base("https://example.com/root"), "https://example.com/root")

    def test_parse_models_payload(self) -> None:
        parsed = MODULE.parse_models_payload('{"data":[{"id":"gpt-5"},{"id":"gpt-5.4"}]}')
        self.assertEqual(parsed["models"], ["gpt-5", "gpt-5.4"])
        self.assertIsNone(parsed["parse_error"])

    def test_extract_text_from_responses_sse(self) -> None:
        body = (
            'event: response.output_text.done\\n'
            'data: {"content_index":0,"text":"ok","type":"response.output_text.done"}\\n'
        )
        self.assertEqual(MODULE.extract_text(body), "ok")

    def test_classify_support(self) -> None:
        classification = MODULE.classify_support(
            [{"model": "gpt-5.4", "success": False}],
            [{"model": "gpt-5.4", "success": True}],
            [{"model": "claude-sonnet-4-5-20250929", "success": False}],
        )
        self.assertEqual(classification["recommended_cch_provider_types"], ["codex"])
        self.assertFalse(classification["supports_openai_chat"])
        self.assertTrue(classification["supports_openai_responses"])

    def test_resolve_api_key_from_env(self) -> None:
        api_key, source = MODULE.resolve_api_key(None, "RELAY_API_KEY", {"RELAY_API_KEY": "secret"})
        self.assertEqual(api_key, "secret")
        self.assertEqual(source, "env:RELAY_API_KEY")

    def test_resolve_api_key_prefers_inline(self) -> None:
        api_key, source = MODULE.resolve_api_key("inline-secret", "RELAY_API_KEY", {"RELAY_API_KEY": "other"})
        self.assertEqual(api_key, "inline-secret")
        self.assertEqual(source, "inline")


if __name__ == "__main__":
    unittest.main()
