"""Request construction and offline doubles, never a DeepSeek live validation."""
import copy
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.loop import run
from investigator.providers import ChatCompletionsProvider, DeepSeekProvider, selection

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "examples/simulation_bundle"
CANARY = "OFFLINE_PRIVATE_REASONING_CANARY_MUST_NOT_BE_SAVED"


def body(message):
    return {"choices": [{"message": {**message, "reasoning_content": CANARY}}]}


class NonThinkingTests(unittest.TestCase):
    def test_generic_default_does_not_add_deepseek_options(self):
        requests = []
        def transport(request, *, timeout_seconds):
            requests.append(copy.deepcopy(request))
            return body(selection(1, "inspect_schema", {}, "Inspect schema"))
        provider = ChatCompletionsProvider(transport, model="offline", allow_data_sharing=True)
        provider.next([{"role": "user", "content": "Test"}], [], 7)
        self.assertNotIn("thinking", requests[0])
        self.assertNotIn("extra_body", requests[0])
        self.assertNotIn("reasoning_effort", requests[0])
        self.assertNotIn("strict", json.dumps(requests[0]))

    def test_explicit_disabled_is_sent_each_turn_and_hidden_reasoning_is_not_retained(self):
        requests = []
        def transport(request, *, timeout_seconds):
            requests.append(copy.deepcopy(request))
            self.assertEqual(request["thinking"], {"type": "disabled"})
            self.assertGreater(timeout_seconds, 0)
            if len(requests) == 1:
                return body(selection(1, "query", {"sql": "SELECT COUNT(*) AS n FROM simulation_runs"}, "Count rows"))
            self.assertEqual(request["messages"][-1]["tool_call_id"], "call_1")
            self.assertNotIn(CANARY, json.dumps(request))
            return body(selection(2, "finish", {"status": "answered", "summary": "Counted the rows.",
                "findings": [{"text": "Actual query result is available.", "evidence": ["e001"]}],
                "questions": []}, "Report the measured result"))
        provider = ChatCompletionsProvider(transport, model="offline-deepseek-contract", thinking="disabled",
                                           allow_data_sharing=True, max_output_tokens=512)
        provider.mode, provider.label = "mock-scripted", "OFFLINE non-thinking request test"
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=AssertionError("No network")):
            output = Path(directory) / "run"
            result = run("Offline protocol check", BUNDLE, output, provider)
            self.assertEqual(result["status"], "answered")
            self.assertEqual(len(requests), 2)
            self.assertTrue(all(r["max_tokens"] == 512 for r in requests))
            self.assertEqual([o["thinking_requested"] for o in result["provider_observations"]], ["disabled"] * 2)
            for file in output.rglob("*"):
                if file.is_file() and file.suffix not in {".sqlite", ".pyc"}:
                    self.assertNotIn(CANARY, file.read_text())

    def test_unsupported_modes_fail_before_a_transport_call(self):
        for value in ("enabled", True, False, 0, {}, [], "none"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "thinking"):
                ChatCompletionsProvider(lambda *a, **k: self.fail("No dispatch"), model="offline",
                                        allow_data_sharing=True, thinking=value)

    def test_legacy_accounting_keyword_is_preserved_with_disabled_thinking(self):
        calls = []
        def transport(request, *, timeout_seconds, budget_reference):
            calls.append((request, timeout_seconds, budget_reference))
            return body(selection(1, "inspect_schema", {}, "Inspect schema"))
        provider = DeepSeekProvider(transport, model="offline", parent_budget_reference="existing-test-ledger",
                                    thinking="disabled", max_output_tokens=256)
        provider.next([], [], 9)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0]["thinking"], {"type": "disabled"})
        self.assertEqual(calls[0][0]["max_tokens"], 256)
        self.assertEqual(calls[0][1:], (9, "existing-test-ledger"))

    def test_configured_client_uses_extra_body_and_does_not_retry_exceptions(self):
        spec = importlib.util.spec_from_file_location("offline_client", ROOT / "examples/configured_client.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        calls = []
        def create(**request):
            calls.append(copy.deepcopy(request))
            raise RuntimeError(CANARY)
        client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=AssertionError("No network")), \
                patch.object(ChatCompletionsProvider, "mode", "mock-scripted"):
            result = module.investigate_with_client(client, model="offline", bundle=BUNDLE,
                output=Path(directory) / "run", goal="Offline failure contract", allow_data_sharing=True,
                thinking="disabled", max_steps=8, max_output_tokens=1024)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["max_tokens"], 1024)
        self.assertEqual(calls[0]["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertNotIn("thinking", calls[0])
        self.assertEqual(result["provider_requests"], 1)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn(CANARY, json.dumps(result))


if __name__ == "__main__":
    unittest.main()
