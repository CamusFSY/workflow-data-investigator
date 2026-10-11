"""Offline protocol fixtures only; none reconstruct the missing first cedar response."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.loop import normalize, run
from investigator.protocol import InvalidResponse, response_evidence
from investigator.providers import DeepSeekProvider, selection
from investigator.replay import verify

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "delivery_slip"
CANARY = "FAKE-SECRET-HEADER-REASONING-CANARY"


def envelope(message):
    return {
        "id": "offline-response", "object": "chat.completion", "created": 0,
        "model": "offline-stub", "system_fingerprint": "offline-fingerprint",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls", "logprobs": None}],
    }


def message():
    return selection(1, "inspect_schema", {}, "")


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def provider(self, response):
        def transport(request, **kwargs):
            self.assertEqual(request["tool_choice"], "auto")
            # No unsupported provider parameter is silently added to paid requests.
            self.assertNotIn("parallel_tool_calls", request)
            return response
        provider = DeepSeekProvider(transport, model="offline-stub", parent_budget_reference="test-only")
        provider.mode = "mock-scripted"
        provider.label = "OFFLINE protocol fixture; not a model invocation"
        return provider

    def execute(self, response, name):
        output = self.root / name
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            result = run("Offline protocol test", FIXTURE, output, self.provider(response),
                         max_steps=2, max_tool_actions=8)
        return output, result

    def test_nullable_empty_missing_content_and_extra_standard_fields(self):
        for variant in ("null", "empty", "missing", "sdk"):
            with self.subTest(variant=variant):
                msg = message()
                if variant in {"null", "sdk"}:
                    msg["content"] = None
                elif variant == "missing":
                    del msg["content"]
                msg.update(refusal=None, annotations=[], reasoning_content=CANARY)
                response = envelope(msg)
                original = copy.deepcopy(response)
                if variant == "sdk":
                    class SDKResponse:
                        def model_dump(self):
                            return copy.deepcopy(original)
                    response = SDKResponse()
                output, result = self.execute(response, variant)
                self.assertEqual(result["tool_actions"], 1)
                # The fixed stub repeats its ID on turn two; the first valid call still executes.
                self.assertFalse(result["investigation_complete"])
                self.assertEqual(result["failure"]["reason"]["code"], "call_id_reused")
                first = json.loads((output / "trace.jsonl").read_text().splitlines()[0])
                self.assertEqual(first["tool"], "inspect_schema")
                self.assertTrue(first["result"]["ok"])
                self.assertEqual(first["public_note"], "")
                records = [json.loads(line) for line in
                           (output / "response_diagnostics.jsonl").read_text().splitlines()]
                self.assertEqual([r["phase"] for r in records], ["received", "accepted", "received", "rejected"])
                self.assertEqual(records[0]["response"]["first_choice"]["finish_reason"]["value"],
                                 "tool_calls")
                if variant != "sdk":
                    self.assertEqual(response, original)
                self.assert_canary_absent(output)

    def assert_canary_absent(self, output):
        for artifact in output.rglob("*"):
            if artifact.is_file():
                self.assertNotIn(CANARY.encode(), artifact.read_bytes(), str(artifact))

    def test_oversized_batch_rejected_with_evidence_saved_before_validation_and_zero_actions(self):
        msg = message()
        msg["tool_calls"] += [selection(n, "read_context", {"document": "catalog"}, "")["tool_calls"][0]
                              for n in range(2, 6)]
        response = envelope(msg)
        output = self.root / "five-calls"

        def validate_after_capture(candidate):
            receipt = json.loads((output / "response_diagnostics.jsonl").read_text().splitlines()[0])
            self.assertEqual(receipt["phase"], "received")
            self.assertEqual(receipt["assistant_message"]["tool_calls"]["items"], 5)
            return normalize(candidate)

        with patch("investigator.loop.normalize", side_effect=validate_after_capture):
            with patch("investigator.loop.Runtime.call") as tool_call:
                result = run("Offline oversized-batch test", FIXTURE, output,
                             self.provider(response), max_steps=1)
        tool_call.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure"]["phase"], "response_validation")
        self.assertEqual(result["failure"]["reason"],
                         {"code": "tool_calls_invalid", "field": "tool_calls"})
        self.assertEqual(result["tool_actions"], 0)
        self.assertFalse(result["investigation_complete"])
        self.assertIsNone(result["answer"])
        self.assertIn("模型响应无效", (output / "report.html").read_text())
        self.assertIn("尚未执行任何工具动作", (output / "report.html").read_text())
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertIn("response_diagnostics.jsonl", manifest["artifacts"])
        with contextlib.redirect_stdout(io.StringIO()) as replay_output:
            self.assertEqual(verify(output), 0)
        self.assertIn("does not establish a completed investigation", replay_output.getvalue())

    def test_malformed_assistant_fields_have_safe_specific_reasons(self):
        examples = [(None, "message_invalid"), ({}, "tool_calls_invalid")]
        variants = [
            ("tool_calls", [None], "call_invalid"),
            ("function", None, "function_invalid"),
            ("type", "unsupported", "call_type_invalid"),
            ("id", "", "call_id_invalid"),
            ("name", False, "function_name_invalid"),
            ("arguments", {}, "arguments_invalid"),
            ("arguments", '{"bad": ' + CANARY, "arguments_json_invalid"),
            ("content", False, "content_invalid"),
            ("content", 0, "content_invalid"),
            ("content", [], "content_invalid"),
            ("content", {"text": CANARY}, "content_invalid"),
        ]
        for field, value, reason in variants:
            msg = message()
            if field in {"tool_calls", "content"}:
                msg[field] = value
            elif field in {"name", "arguments"}:
                msg["tool_calls"][0]["function"][field] = value
            else:
                msg["tool_calls"][0][field] = value
            examples.append((msg, reason))
        for index, (msg, reason) in enumerate(examples):
            with self.subTest(reason=reason, index=index):
                response = envelope(msg)
                response["request"] = {"headers": {"Authorization": CANARY}}
                response["credentials"] = CANARY
                output, result = self.execute(response, f"malformed-{index}")
                self.assertEqual(result["failure"]["reason"]["code"], reason)
                self.assertEqual(result["tool_actions"], 0)
                self.assertFalse(result["investigation_complete"])
                self.assert_canary_absent(output)

    def test_malformed_envelopes_keep_bounded_structural_evidence(self):
        cases = [
            (None, "response_not_object"), ([], "response_not_object"),
            ({}, "choices_invalid"), ({"choices": []}, "choices_invalid"),
            ({"choices": [None]}, "choice_invalid"),
        ]
        for index, (response, reason) in enumerate(cases):
            with self.subTest(reason=reason, index=index):
                output, result = self.execute(response, f"envelope-{index}")
                self.assertEqual(result["failure"]["reason"]["code"], reason)
                self.assertEqual(result["tool_actions"], 0)
                records = [json.loads(line) for line in
                           (output / "response_diagnostics.jsonl").read_text().splitlines()]
                self.assertEqual(records[0]["phase"], "rejected")
                self.assertIsInstance(records[0]["response"], dict)

    def test_structural_projection_omits_free_text_headers_and_is_bounded(self):
        msg = message()
        msg["content"] = CANARY * 50000
        msg["reasoning_content"] = CANARY
        msg["tool_calls"][0]["id"] = CANARY
        msg["tool_calls"][0]["function"]["arguments"] = CANARY * 1000
        msg["tool_calls"] *= 1000
        body = envelope(msg)
        body["headers"] = {"Authorization": CANARY}
        body["request"] = {"api_key": CANARY}
        snapshot = response_evidence(body)
        encoded = json.dumps(snapshot).encode()
        self.assertLess(len(encoded), 8192)
        self.assertNotIn(CANARY.encode(), encoded)
        calls = snapshot["first_choice"]["message"]["tool_calls"]
        self.assertEqual(calls["items"], 1000)
        self.assertEqual(len(calls["sample"]), 4)
        self.assertTrue(calls["sample_truncated"])

    def test_parent_can_preserve_a_rejection_without_exposing_raw_body(self):
        msg = message()
        msg["content"] = {"text": CANARY}
        body = envelope(msg)
        body["request"] = {"headers": {"Authorization": CANARY}}

        def transport(request, **kwargs):
            # Parent keeps its original settlement, then validates. No ledger here.
            try:
                normalize(body["choices"][0]["message"])
            except InvalidResponse as exc:
                raise InvalidResponse(exc.reason["code"], call_index=exc.call_index, response=body) from None
            self.fail("Malformed fixture must be rejected")

        provider = self.provider(None)
        provider.transport = transport
        output = self.root / "parent-rejection"
        result = run("Offline parent contract test", FIXTURE, output, provider, max_steps=1)
        self.assertEqual(result["failure"]["reason"]["code"], "content_invalid")
        self.assertEqual(result["tool_actions"], 0)
        records = [json.loads(line) for line in
                   (output / "response_diagnostics.jsonl").read_text().splitlines()]
        self.assertEqual(records[0]["response"]["first_choice"]["message"]["content"],
                         {"type": "object", "fields": 1})
        self.assert_canary_absent(output)


if __name__ == "__main__":
    unittest.main()
