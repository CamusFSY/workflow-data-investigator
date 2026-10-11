"""Offline callback/SDK doubles only; these tests are not live model validation."""
import copy
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.loop import run
from investigator.mock import ScriptedMock
from investigator.providers import ChatCompletionsProvider, TransportFailure, TransportResponse, selection
from investigator.replay import verify

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "examples" / "simulation_bundle"
CANARY = "FAKE_AUTH_PRIVATE_REASONING_CANARY"


def envelope(message):
    return {"model": "offline-response-model", "choices": [{"message": message}]}


def clarification(number=2):
    return selection(number, "finish", {
        "status": "needs_clarification", "summary": "An eligibility decision is still missing.",
        "findings": [{"text": "The supplied metric text is the available authority.", "evidence": ["e001"]}],
        "questions": ["Should cancelled simulation runs be included in the denominator?"],
    }, "Ask the caller for the missing decision.")


class PublicProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def adapter(self, transport):
        provider = ChatCompletionsProvider(transport, model="offline-contract-test", allow_data_sharing=True)
        provider.label = "OFFLINE contract test of live adapter fields; no network"
        return provider

    def execute(self, provider, name="run", **limits):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            return run("Offline provider contract test", BUNDLE, self.root / name, provider, **limits)

    def test_complete_contract_is_checked_before_input_output_or_tools(self):
        valid = {"mode": "mock-scripted", "label": "Offline contract", "next": lambda *a: None}
        invalid = [{k: v for k, v in valid.items() if k != missing} for missing in valid]
        invalid += [{**valid, "mode": v} for v in (None, [], "hidden")]
        invalid += [{**valid, "label": v} for v in (None, "", "x" * 201, "x\nheader", "\ud800")]
        invalid += [{**valid, "next": None}]
        for i, attributes in enumerate(invalid):
            with self.subTest(attributes=list(attributes)), patch("investigator.loop.prepare_bundle") as prepare:
                with self.assertRaises(ValueError):
                    self.execute(types.SimpleNamespace(**attributes), f"bad-{i}")
                prepare.assert_not_called()
                self.assertFalse((self.root / f"bad-{i}").exists())

    def test_contract_snapshot_survives_label_mode_removal_and_later_provider_failure(self):
        class Provider:
            def __init__(self):
                self.mode, self.label, self.count = "mock-scripted", "Original offline label", 0

            def next(self, messages, tools, timeout_seconds):
                self.count += 1
                if self.count == 1:
                    del self.mode, self.label
                    return selection(1, "query", {"sql": "SELECT COUNT(*) AS n FROM simulation_runs"}, "Count actual rows.")
                raise RuntimeError("Authorization: " + CANARY)

        result = self.execute(Provider())
        self.assertEqual(result["provider"], "Original offline label")
        self.assertEqual(result["mode"], "mock-scripted")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["tool_actions"], 1)
        self.assertEqual(result["provider_activity"]["responses_received"], 1)
        self.assertEqual([o["response_received"] for o in result["provider_observations"]], [True, False])
        self.assertTrue((self.root / "run" / "report.html").is_file())
        self.assertEqual(verify(self.root / "run"), 1)
        self.assert_canary_absent(self.root / "run")

    def test_minimal_provider_returns_are_counted_without_optional_receipts(self):
        class Provider:
            mode, label = "mock-scripted", "Minimal offline provider"

            def next(self, messages, tools, timeout_seconds):
                if not any(message["role"] == "tool" for message in messages):
                    return selection(1, "read_context", {"document": "metric"}, "Read the definition.")
                return clarification()

        result = self.execute(Provider())
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["provider_activity"]["responses_received"], 2)
        self.assertEqual(result["provider_activity"]["dispatch_unknown"], 2)
        self.assertEqual(result["live_request_attempts"], 0)
        self.assertTrue(all(o["response_received"] for o in result["provider_observations"]))
        self.assertEqual(verify(self.root / "run"), 2)

    def test_legacy_scripted_provider_returns_are_counted(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            result = run("Check the missing definition", ROOT / "fixtures/missing_definition",
                         self.root / "scripted", ScriptedMock())
        self.assertEqual(result["status"], "needs_clarification")
        self.assertGreater(result["provider_requests"], 0)
        self.assertEqual(result["provider_activity"]["responses_received"], result["provider_requests"])
        self.assertEqual(result["provider_activity"]["dispatch_unknown"], result["provider_requests"])
        self.assertEqual(result["live_request_attempts"], 0)
        self.assertTrue(all(o["response_received"] for o in result["provider_observations"]))

    def test_explicit_data_sharing_is_required_without_touching_transport(self):
        for value in (False, None, 1, "true"):
            with self.subTest(value=value), patch("socket.socket", side_effect=AssertionError("Network forbidden")):
                with self.assertRaisesRegex(ValueError, "allow_data_sharing=True"):
                    ChatCompletionsProvider(lambda *a, **k: self.fail("Must not dispatch"),
                                            model="offline", allow_data_sharing=value)

    def test_rejected_budget_and_unknown_dispatch_are_separate_from_attempts(self):
        for reported in (False, None):
            def reject(request, *, timeout_seconds):
                if reported is False:
                    raise TransportFailure("budget_rejected", dispatched=False)
                raise RuntimeError("Authorization: " + CANARY)
            result = self.execute(self.adapter(reject), str(reported))
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["tool_actions"], 0)
            self.assertEqual(result["provider_requests"], 1)
            self.assertEqual(result["live_calls"], 1)  # Legacy attempts alias, never a billing claim.
            self.assertEqual(result["live_request_attempts"], 1)
            activity = result["provider_activity"]
            self.assertEqual(activity["responses_received"], 0)
            self.assertEqual(activity["reported_dispatched"], 0)
            self.assertEqual(activity["reported_not_dispatched"], int(reported is False))
            self.assertEqual(activity["dispatch_unknown"], int(reported is None))
            if reported is False:
                self.assertEqual(result["provider_observations"][0]["rejection_reason"], "budget_rejected")
            self.assert_canary_absent(self.root / str(reported))

    def test_returned_identity_usage_survive_malformed_message_without_private_fields(self):
        response = {
            "model": "offline-model-v2", "choices": [],
            "usage": {"prompt_tokens": 17, "completion_tokens": 4, "total_tokens": 21,
                      "prompt_cache_hit_tokens": True, "prompt_cache_miss_tokens": -1,
                      "reasoning": CANARY, "headers": {"Authorization": CANARY}},
            "headers": {"Authorization": CANARY}, "reasoning_content": CANARY,
        }
        provider = self.adapter(lambda request, **kwargs: TransportResponse(response, dispatched=True))
        result = self.execute(provider)
        self.assertEqual(result["failure"]["reason"]["code"], "choices_invalid")
        observation = result["provider_observations"][0]
        self.assertEqual(observation["requested_model"], "offline-contract-test")
        self.assertEqual(observation["response_model"], "offline-model-v2")
        self.assertEqual(observation["usage"], {"prompt_tokens": 17, "completion_tokens": 4, "total_tokens": 21})
        self.assertEqual(observation["dispatch_status"], "reported_dispatched")
        self.assertEqual(result["provider_activity"]["responses_received"], 1)
        self.assert_canary_absent(self.root / "run")

    def test_neutral_adapter_preserves_feedback_ids_finalization_schema_and_timeout(self):
        requests = []
        def transport(request, *, timeout_seconds):
            requests.append(copy.deepcopy(request))
            self.assertGreater(timeout_seconds, 0)
            self.assertLessEqual(timeout_seconds, 60)
            self.assertNotIn("parallel_tool_calls", request)
            if len(requests) == 1:
                return envelope(selection(1, "read_context", {"document": "metric"}, "Read the definition."))
            self.assertEqual([t["function"]["name"] for t in request["tools"]], ["finish"])
            self.assertEqual(request["messages"][-1]["tool_call_id"], "call_1")
            self.assertEqual(json.loads(request["messages"][-1]["content"])["evidence_id"], "e001")
            return envelope(clarification())
        result = self.execute(self.adapter(transport), max_steps=2, max_tool_actions=8)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["provider_activity"]["dispatch_unknown"], 2)
        self.assertEqual(result["provider_activity"]["responses_received"], 2)
        self.assertFalse(result["investigation_complete"])
        self.assertTrue(result["clarifications"])

    def test_public_configured_client_example_import_opt_in_and_protocol(self):
        spec = importlib.util.spec_from_file_location("configured_client_example", ROOT / "examples/configured_client.py")
        module = importlib.util.module_from_spec(spec)
        class NoClientAccess:
            @property
            def chat(self):
                raise AssertionError("Client touched without opt-in")
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            spec.loader.exec_module(module)
            with self.assertRaisesRegex(ValueError, "allow_data_sharing=True"):
                module.investigate_with_client(NoClientAccess(), model="offline-sdk-test",
                    bundle=BUNDLE, output=self.root / "no-opt-in", goal="Contract test")
        self.assertFalse((self.root / "no-opt-in").exists())
        bodies = json.loads((ROOT / "examples/simulation_responses.json").read_text())["responses"]
        calls = []
        def create(**request):
            calls.append(copy.deepcopy(request))
            self.assertGreater(request["timeout"], 0)
            response = copy.deepcopy(bodies[len(calls) - 1])
            response["choices"][0]["message"]["reasoning_content"] = CANARY
            response["headers"] = {"Authorization": CANARY}
            return types.SimpleNamespace(model_dump=lambda: response)
        client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")), \
                patch.object(ChatCompletionsProvider, "mode", "mock-scripted"), \
                patch.object(ChatCompletionsProvider, "label", "OFFLINE configured-client contract test"):
            result = module.investigate_with_client(client, model="offline-sdk-test",
                bundle=BUNDLE, output=self.root / "sdk-double", goal="Offline SDK contract test",
                allow_data_sharing=True)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["tool_actions"], 9)
        observed_error = json.loads(calls[2]["messages"][-1]["content"])
        self.assertFalse(observed_error["ok"])
        self.assertIn("reporting_week", observed_error["error"]["message"])
        self.assertEqual(calls[2]["messages"][-1]["tool_call_id"], "example_4")
        self.assertEqual(verify(self.root / "sdk-double"), 9)
        self.assert_canary_absent(self.root / "sdk-double")

    def assert_canary_absent(self, output):
        for file in output.rglob("*"):
            if file.is_file():
                self.assertNotIn(CANARY.encode(), file.read_bytes(), str(file))


if __name__ == "__main__":
    unittest.main()
