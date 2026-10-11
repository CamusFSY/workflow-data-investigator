"""Synthetic offline responses, not reconstruction of either cedar live response."""
import contextlib
import copy
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.bundle import digest
from investigator.loop import normalize, run
from investigator.protocol import InvalidResponse, extract_message
from investigator.providers import DeepSeekProvider, selection
from investigator.replay import verify

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "delivery_slip"
CANARY = "BATCH-PRIVATE-REASONING-CANARY"


def call(number, name="inspect_schema", args=None):
    return selection(number, name, {} if args is None else args, "")["tool_calls"][0]


def batch(*calls):
    return {"role": "assistant", "content": None, "tool_calls": list(calls),
            "reasoning_content": CANARY}


def four_calls():
    # Only the count matches the observed diagnostic. All IDs, args and the fourth
    # tool below are locally authored fixture choices, not retained live values.
    return batch(call(1, "read_context", {"document": "catalog"}),
                 call(2, "read_context", {"document": "metric"}),
                 call(3, "read_context", {"document": "request"}), call(4))


def finish(number, evidence="e001"):
    return call(number, "finish", {
        "status": "answered", "summary": "Synthetic offline protocol count",
        "findings": [{"text": "The development fixture contains 42 orders.", "evidence": [evidence]}],
        "questions": [],
    })


class BatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        network = patch("socket.socket", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def provider(self, choose):
        requests = []

        def transport(payload, **kwargs):
            requests.append(copy.deepcopy(payload))
            self.assertNotIn("parallel_tool_calls", payload)
            self.assertEqual(payload["max_tokens"], 2048)
            self.assertEqual(payload["tool_choice"], "auto")
            message = choose(len(requests), payload["messages"])
            return {"choices": [{"message": message, "finish_reason": "tool_calls"}]}

        provider = DeepSeekProvider(transport, model="offline-stub", parent_budget_reference="test-only")
        provider.mode = "mock-scripted"
        provider.label = "SCRIPTED offline batch fixture; no model invocation"
        return provider, requests

    def trace(self, output):
        return [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]

    def test_four_calls_then_observed_error_repair_feedback_and_replay(self):
        def choose(turn, messages):
            if turn == 1:
                return four_calls()
            if turn == 2:
                self.assertEqual([m["tool_call_id"] for m in messages[-4:]],
                                 [f"call_{n}" for n in range(1, 5)])
                self.assertTrue(all(m["role"] == "tool" for m in messages[-4:]))
                self.assertEqual(len(messages[-5]["tool_calls"]), 4)
                self.assertTrue(all(json.loads(m["content"])["ok"] for m in messages[-4:]))
                return batch(call(5, "query", {"sql": "SELECT missing_column FROM orders"}), call(6))
            if turn == 3:
                bad, schema = [json.loads(m["content"]) for m in messages[-2:]]
                self.assertEqual([m["tool_call_id"] for m in messages[-2:]], ["call_5", "call_6"])
                self.assertFalse(bad["ok"])
                self.assertIn("missing_column", bad["error"]["message"])
                self.assertIn("orders", [t["name"] for t in schema["data"]["tables"]])
                return batch(call(7, "query", {"sql": "SELECT COUNT(*) AS n FROM orders"}))
            self.assertEqual(turn, 4)
            evidence = json.loads(messages[-1]["content"])
            self.assertEqual(evidence["data"]["rows"], [{"n": 42}])
            return batch(finish(8, evidence["evidence_id"]))

        provider, requests = self.provider(choose)
        output = self.root / "feedback"
        result = run("Synthetic batch protocol test", FIXTURE, output, provider,
                     max_steps=4, max_tool_actions=12)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["tool_actions"], 8)
        self.assertTrue(result["investigation_complete"])
        self.assertEqual(result["live_calls"], 0)
        self.assertEqual(len(requests), 4)
        events = self.trace(output)
        self.assertEqual([e["evidence_id"] for e in events], [f"e{n:03d}" for n in range(1, 9)])
        self.assertEqual([e["tool_call_id"] for e in events], [f"call_{n}" for n in range(1, 9)])
        self.assertEqual([e["model_turn"] for e in events], [1, 1, 1, 1, 2, 2, 3, 4])
        self.assertEqual([e["batch_index"] for e in events], [0, 1, 2, 3, 0, 1, 0, 0])
        receipt = json.loads((output / "response_diagnostics.jsonl").read_text().splitlines()[0])
        calls = receipt["response"]["first_choice"]["message"]["tool_calls"]
        self.assertEqual(len(calls["sample"]), 4)
        self.assertFalse(calls["sample_truncated"])
        self.assertNotIn(CANARY, json.dumps(requests))
        for artifact in output.rglob("*"):
            if artifact.is_file():
                self.assertNotIn(CANARY.encode(), artifact.read_bytes())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(output), 8)
        # Execute the exported notebook's actual trusted cells, from its own directory.
        notebook_run = subprocess.run([sys.executable, "-c",
            "import json\nbook=json.load(open('investigation.ipynb'))\n"
            "for c in book['cells']:\n    if c['cell_type']=='code': exec(''.join(c['source']))\n"],
            cwd=output, text=True, capture_output=True, timeout=10)
        self.assertEqual(notebook_run.returncode, 0, notebook_run.stderr)

    def test_malformed_fourth_call_prevents_every_call_in_batch(self):
        variants = [
            (None, "call_invalid", "tool_calls[3]"),
            ({**call(4), "function": None}, "function_invalid", "tool_calls[3].function"),
            (call(4, "query", {}), "arguments_schema_invalid", "tool_calls[3].function.arguments"),
            (call(4, "read_context", {"document": "private"}), "arguments_schema_invalid",
             "tool_calls[3].function.arguments"),
            (call(4, "inspect_schema", {"unexpected": CANARY}), "arguments_schema_invalid",
             "tool_calls[3].function.arguments"),
            (call(4, CANARY), "tool_unknown", "tool_calls[3].function.name"),
            (call(1), "call_id_reused", "tool_calls[3].id"),
        ]
        for raw, reason in [("[", "arguments_json_invalid"), ({}, "arguments_invalid"),
                            ("[]", "arguments_schema_invalid"), ('"' + CANARY + '"', "arguments_schema_invalid"),
                            ("\ud800", "arguments_invalid")]:
            invalid = call(4)
            invalid["function"]["arguments"] = raw
            variants.append((invalid, reason, "tool_calls[3].function.arguments"))
        for index, (invalid, code, field) in enumerate(variants):
            with self.subTest(code=code, index=index):
                msg = four_calls()
                msg["tool_calls"][3] = invalid
                provider, requests = self.provider(lambda *_: msg)
                output = self.root / f"invalid-{index}"
                with patch("investigator.loop.Runtime.call") as execute:
                    result = run("Reject entire synthetic batch", FIXTURE, output, provider,
                                 max_steps=1, max_tool_actions=4)
                execute.assert_not_called()
                self.assertEqual(result["tool_actions"], 0)
                self.assertEqual(len(requests), 1)
                self.assertEqual(result["failure"]["reason"], {"code": code, "field": field})
                self.assertEqual([e["tool"] for e in self.trace(output)], ["run_error"])
                self.assertNotIn(CANARY, (output / "response_diagnostics.jsonl").read_text())

    def test_finish_must_be_alone_including_multiple_terminals(self):
        for index, msg in enumerate([batch(finish(1), call(2)), batch(call(1), finish(2)),
                                     batch(finish(1), finish(2))]):
            provider, _ = self.provider(lambda *_: msg)
            with patch("investigator.loop.Runtime.call") as execute:
                result = run("Terminal batch test", FIXTURE, self.root / f"finish-{index}", provider,
                             max_steps=1, max_tool_actions=4)
            execute.assert_not_called()
            self.assertEqual(result["failure"]["reason"]["code"], "terminal_batch_invalid")
            self.assertFalse(result["investigation_complete"])

    def test_reused_id_in_later_batch_prevents_its_fresh_call_too(self):
        provider, requests = self.provider(lambda n, _: batch(call(1)) if n == 1
                                            else batch(call(2), call(1)))
        output = self.root / "reused"
        result = run("ID reuse test", FIXTURE, output, provider, max_steps=3, max_tool_actions=8)
        self.assertEqual(result["tool_actions"], 1)
        self.assertEqual(len(requests), 2)
        self.assertEqual(result["failure"]["reason"],
                         {"code": "call_id_reused", "field": "tool_calls[1].id"})
        self.assertEqual([e["tool_call_id"] for e in self.trace(output) if e["tool"] != "run_error"],
                         ["call_1"])

    def test_model_turn_and_total_action_caps_are_independent(self):
        cases = [
            ("default-bound", {"max_steps": 1}, lambda *_: four_calls(), 0, 1, "Finalization window"),
            ("turn-bound", {"max_steps": 1, "max_tool_actions": 4}, lambda *_: four_calls(),
             0, 1, "Finalization window"),
            ("action-bound", {"max_steps": 5, "max_tool_actions": 4}, lambda *_: four_calls(),
             0, 1, "Finalization window"),
            ("remaining-bound", {"max_steps": 5, "max_tool_actions": 8},
             lambda n, _: batch(call(n * 2), call(n * 2 + 1)), 4, 3, "no calls in this batch executed"),
        ]
        for name, limits, choose, actions, turns, message in cases:
            with self.subTest(name=name):
                provider, requests = self.provider(choose)
                result = run("Independent limits test", FIXTURE, self.root / name, provider, **limits)
                self.assertEqual(result["tool_actions"], actions)
                self.assertEqual(len(requests), turns)
                self.assertEqual(result["failure"]["phase"], "response_validation")
                self.assertEqual(result["failure"]["reason"]["code"], "finalization_tool_required")
                self.assertIn(message, result["failure"]["message"])
                self.assertFalse(result["investigation_complete"])
                self.assertEqual(result["limits"]["max_tool_actions"], limits.get("max_tool_actions", 1))
        for invalid in [0, -1, 41, 160, True, 1.5]:
            with self.subTest(invalid=invalid):
                provider, requests = self.provider(lambda *_: four_calls())
                with self.assertRaises(ValueError):
                    run("Invalid limit", FIXTURE, self.root / "absent", provider, max_tool_actions=invalid)
                self.assertFalse(requests)
                self.assertFalse((self.root / "absent").exists())

    def test_deadline_between_calls_stops_with_unexecuted_count(self):
        clock = [0.0]
        provider, requests = self.provider(lambda *_: four_calls())

        def elapsed_after_tool(event):
            if event["tool"] != "run_error":
                clock[0] = 2.0

        output = self.root / "deadline"
        with patch("investigator.loop.time.monotonic", side_effect=lambda: clock[0]):
            result = run("Synthetic elapsed clock", FIXTURE, output, provider, max_steps=2,
                         max_tool_actions=8, max_seconds=1, on_event=elapsed_after_tool)
        self.assertEqual(result["tool_actions"], 1)
        self.assertEqual(result["failure"]["type"], "TimeoutError")
        self.assertEqual(result["failure"]["unexecuted_tool_calls"], 3)
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(self.trace(output)), 2)

    def test_context_limit_is_checked_inside_batch_without_fake_remaining_results(self):
        fixture = self.root / "large-context"
        shutil.copytree(FIXTURE, fixture)
        (fixture / "metric_definition.md").write_text("\n" * 64000)
        provider, requests = self.provider(lambda *_: batch(*[
            call(n, "read_context", {"document": "metric"}) for n in range(1, 5)]))
        output = self.root / "context-limit"
        result = run("Large synthetic context test", fixture, output, provider,
                     max_steps=4, max_tool_actions=8)
        self.assertEqual(result["failure"]["phase"], "run_limits")
        self.assertIn("Context exceeds", result["failure"]["message"])
        self.assertEqual(result["tool_actions"], 2)
        self.assertEqual(result["failure"]["unexecuted_tool_calls"], 2)
        self.assertEqual(len(requests), 1)
        self.assertEqual([e.get("tool_call_id") for e in self.trace(output)], ["call_1", "call_2", None])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(output), 2)

    def test_readonly_sql_errors_remain_real_feedback_in_valid_batches(self):
        output = self.root / "readonly"
        original = []

        def choose(turn, messages):
            if turn == 1:
                original.append(digest((output / "input" / "data.sqlite").read_bytes()))
                return batch(call(1, "query", {"sql": "DROP TABLE orders"}),
                             call(2, "query", {"sql": "SELECT COUNT(*) AS n FROM orders"}))
            self.assertFalse(json.loads(messages[-2]["content"])["ok"])
            self.assertEqual(json.loads(messages[-1]["content"])["data"]["rows"], [{"n": 42}])
            return batch(finish(3, "e002"))

        provider, requests = self.provider(choose)
        result = run("Read-only batch test", FIXTURE, output, provider, max_steps=2, max_tool_actions=8)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["tool_actions"], 3)
        self.assertEqual(len(requests), 2)
        self.assertEqual(digest((output / "input" / "data.sqlite").read_bytes()), original[0])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(output), 3)

    def test_parent_prevalidation_keeps_fourth_call_reason(self):
        msg = four_calls()
        msg["tool_calls"][3] = call(4, "query", {})
        body = {"choices": [{"message": msg}]}
        provider, _ = self.provider(lambda *_: msg)

        def parent_transport(*args, **kwargs):
            try:
                normalize(extract_message(body))
            except InvalidResponse as exc:
                raise InvalidResponse(exc.reason["code"], call_index=exc.call_index, response=body) from None

        provider.transport = parent_transport
        output = self.root / "parent-prevalidation"
        result = run("Parent contract test", FIXTURE, output, provider, max_steps=1, max_tool_actions=4)
        self.assertEqual(result["tool_actions"], 0)
        self.assertEqual(result["failure"]["reason"]["field"], "tool_calls[3].function.arguments")
        receipt = json.loads((output / "response_diagnostics.jsonl").read_text().splitlines()[0])
        self.assertEqual(len(receipt["response"]["first_choice"]["message"]["tool_calls"]["sample"]), 4)


if __name__ == "__main__":
    unittest.main()
