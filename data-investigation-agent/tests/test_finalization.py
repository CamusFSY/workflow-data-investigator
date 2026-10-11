"""SCRIPTED, synthetic finalization regressions; not a reconstruction of a live response."""
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.loop import run
from investigator.providers import DeepSeekProvider, selection
from investigator.replay import verify

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "missing_definition"


def call(number, name, args):
    return selection(number, name, args, "SCRIPTED finalization check")["tool_calls"][0]


def batch(*calls):
    return {"role": "assistant", "content": "SCRIPTED local protocol test", "tool_calls": list(calls)}


def finish(number=22, status="needs_clarification", refs=("e001", "e005")):
    return batch(call(number, "finish", {
        "status": status, "summary": "Synthetic count measured; metric authority remains unresolved.",
        "findings": [{"text": "The local fixture's table count does not establish metric eligibility.",
                      "evidence": list(refs)}],
        "questions": ["Which denominator is approved for this metric?"],
        "conditions": ["Assume all table rows are eligible."] if status == "conditional" else [],
    }))


def prefix():
    """Locally authored 4/4/3/3/3/4 sequence, with returned aggregates reused."""
    rates = {"period": "period", "baseline": "baseline", "current": "current",
             "successes": "on_time", "total": "total", "operation": "compare_rates"}
    return [
        batch(call(1, "read_context", {"document": "metric"}),
              call(2, "read_context", {"document": "catalog"}),
              call(3, "read_context", {"document": "request"}), call(4, "inspect_schema", {})),
        batch(call(5, "query", {"sql": "SELECT COUNT(*) AS n FROM orders"}),
              call(6, "query", {"sql": "SELECT 'baseline' AS period, 3 AS on_time, 4 AS total "
                    "UNION ALL SELECT 'current', 2, 4"}),
              call(7, "query", {"sql": "SELECT COUNT(*) AS n FROM shipments"}),
              call(8, "read_context", {"document": "dashboard"})),
        batch(call(9, "analyze", {**rates, "evidence_id": "e006"}),
              call(10, "plot", {"evidence_id": "e006", "label": "period", "successes": "on_time", "total": "total"}),
              call(11, "inspect_schema", {})),
        batch(*[call(i, "read_context", {"document": doc})
                for i, doc in zip(range(12, 15), ["request", "catalog", "metric"], strict=True)]),
        batch(call(15, "inspect_schema", {}),
              call(16, "read_context", {"document": "dashboard"}),
              call(17, "read_context", {"document": "metric"})),
        batch(call(18, "analyze", {**rates, "evidence_id": "e018"}),
              call(19, "plot", {"evidence_id": "e020", "label": "period", "successes": "on_time", "total": "total"}),
              call(20, "analyze", {**rates, "evidence_id": "e999"}),
              call(21, "plot", {"evidence_id": "e021", "label": "period", "successes": "on_time", "total": "total"})),
    ]


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        network = patch("socket.socket", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def provider(self, responses, before_return=None):
        requests = []

        def transport(payload, **kwargs):
            requests.append(copy.deepcopy(payload))
            self.assertEqual(payload["tool_choice"], "auto")
            self.assertEqual(payload["max_tokens"], 2048)
            self.assertNotIn("parallel_tool_calls", payload)
            self.assertEqual(kwargs["budget_reference"], "offline-test-only")
            if before_return:
                before_return(len(requests))
            return {"choices": [{"message": copy.deepcopy(responses[len(requests) - 1])}]}

        provider = DeepSeekProvider(transport, model="offline-stub", parent_budget_reference="offline-test-only")
        provider.mode = "mock-scripted"
        provider.label = "SCRIPTED finalization regression; no model invocation"
        return provider, requests

    def events(self, output):
        return [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]

    def budgets(self, requests):
        return [json.loads(r["messages"][0]["content"].split("Current decision budget: ", 1)[1])
                for r in requests]

    def test_error_prefix_then_lone_clarification_uses_existing_evidence(self):
        provider, requests = self.provider([*prefix(), finish()])
        output = self.root / "clarification"
        result = run("Synthetic finalization test", FIXTURE, output, provider,
                     max_steps=16, max_tool_actions=24, max_seconds=120)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertFalse(result["investigation_complete"])
        self.assertEqual((result["tool_actions"], result["provider_requests"], result["live_calls"]), (22, 7, 0))
        self.assertEqual((result["limits"]["max_steps"], result["limits"]["max_tool_actions"],
                          result["limits"]["max_seconds"]), (16, 24, 120))
        events = self.events(output)
        self.assertEqual([sum(e["model_turn"] == n for e in events) for n in range(1, 8)],
                         [4, 4, 3, 3, 3, 4, 1])
        self.assertTrue(all(not e["result"]["ok"] for e in events[17:21]))
        self.assertTrue(all("successful query evidence_id" in e["result"]["error"]["message"]
                            for e in events[17:21]))
        self.assertEqual([e["evidence_id"] for e in events if e["tool"] == "query"], ["e005", "e006", "e007"])
        self.assertEqual(events[8]["input"]["evidence_id"], "e006")
        self.assertTrue(events[8]["result"]["ok"] and events[9]["result"]["ok"])
        self.assertEqual(events[-1]["input"]["findings"][0]["evidence"], ["e001", "e005"])
        budgets = self.budgets(requests)
        self.assertEqual([b["remaining_tool_actions"] for b in budgets], [24, 20, 16, 13, 10, 7, 3])
        self.assertEqual([b["remaining_model_turns"] for b in budgets], [16, 15, 14, 13, 12, 11, 10])
        self.assertEqual([b["finish_only"] for b in budgets], [False] * 6 + [True])
        self.assertEqual([t["function"]["name"] for t in requests[-1]["tools"]], ["finish"])
        self.assertTrue(all(len(r["tools"]) == 6 for r in requests[:-1]))
        self.assertEqual(events[-1]["decision_budget"], budgets[-1])
        final_feedback = requests[-1]["messages"][-4:]
        self.assertEqual([m["tool_call_id"] for m in final_feedback], [f"call_{i}" for i in range(18, 22)])
        self.assertTrue(all(not json.loads(m["content"])["ok"] for m in final_feedback))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(output), 22)
        completed = subprocess.run([sys.executable, "-I", "-c",
            "import json\nbook=json.load(open('investigation.ipynb'))\n"
            "for c in book['cells']:\n if c['cell_type']=='code': exec(''.join(c['source']))\n"],
            cwd=output, text=True, capture_output=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_21_of_24_rejects_entire_three_query_batch_without_retry(self):
        extra = batch(*[call(i, "query", {"sql": "SELECT COUNT(*) AS n FROM orders"}) for i in range(22, 25)])
        provider, requests = self.provider([*prefix(), extra, finish(25)])
        output = self.root / "ignored"
        result = run("Synthetic ignored finish restriction", FIXTURE, output, provider,
                     max_steps=16, max_tool_actions=24, max_seconds=120)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["answer"])
        self.assertEqual((result["tool_actions"], len(requests)), (21, 7))
        self.assertEqual(result["failure"]["reason"]["code"], "finalization_tool_required")
        self.assertEqual(self.events(output)[-1]["tool"], "run_error")
        self.assertFalse(any(e.get("tool_call_id") in {"call_22", "call_23", "call_24"} for e in self.events(output)))

    def test_final_model_turn_offers_and_enforces_only_finish(self):
        first = batch(call(1, "query", {"sql": "SELECT COUNT(*) AS n FROM orders"}))
        for name, last, status in [
            ("valid", finish(2, "conditional", ["e001"]), "conditional"),
            ("ignored", batch(call(2, "inspect_schema", {})), "failed"),
        ]:
            provider, requests = self.provider([first, last])
            result = run("Synthetic last-turn test", FIXTURE, self.root / name, provider,
                         max_steps=2, max_tool_actions=24)
            self.assertEqual(result["status"], status)
            self.assertEqual(len(requests), 2)
            self.assertEqual(self.budgets(requests)[-1]["remaining_model_turns"], 1)
            self.assertEqual(self.budgets(requests)[-1]["remaining_tool_actions"], 23)
            self.assertEqual([t["function"]["name"] for t in requests[-1]["tools"]], ["finish"])
            self.assertFalse(result["investigation_complete"])
            if status == "conditional":
                self.assertTrue(result["answer"]["conditions"] and result["answer"]["questions"])
                self.assertIn("条件性结果", (self.root / name / "report.html").read_text())

    def test_invalid_finish_in_window_keeps_error_and_stops_without_resolver_or_retry(self):
        first = batch(call(1, "query", {"sql": "SELECT COUNT(*) AS n FROM orders"}))
        for name, last in [
            ("reference", finish(2, refs=["e999"])),
            ("blocker", finish(2, "answered", ["e001"])),
            ("schema", batch(call(2, "finish", {"status": "answered"}))),
        ]:
            provider, requests = self.provider([first, last, finish(3)])
            output = self.root / name
            with patch("investigator.loop.Runtime.apply_clarifications") as resolve:
                result = run("Synthetic invalid finish", FIXTURE, output, provider,
                             max_steps=16, max_tool_actions=5,
                             clarification_resolver=lambda _: self.fail("No callback after finalization rejection"))
            resolve.assert_not_called()
            self.assertEqual(result["status"], "failed")
            self.assertEqual(len(requests), 2)
            self.assertIsNone(result["answer"])
            if name != "schema":
                self.assertEqual(result["failure"]["phase"], "finalization_window")
                self.assertEqual(result["tool_actions"], 2)
                self.assertFalse(self.events(output)[-2]["result"]["ok"])
                self.assertTrue(result["clarifications"])
            else:
                self.assertEqual(result["tool_actions"], 1)
                self.assertEqual(result["failure"]["reason"]["code"], "arguments_schema_invalid")

    def test_deadline_at_window_never_adds_request_or_promotes_answer(self):
        for point, expected_requests, expected_actions in [("before", 6, 21), ("provider", 7, 21), ("after", 7, 22)]:
            clock = [0.0]

            def before_return(number):
                if point == "provider" and number == 7:
                    clock[0] = 121.0

            def on_event(event):
                if ((point == "before" and event["evidence_id"] == "e021") or
                        (point == "after" and event["evidence_id"] == "e022")):
                    clock[0] = 121.0

            provider, requests = self.provider([*prefix(), finish()], before_return)
            output = self.root / point
            with patch("investigator.loop.time.monotonic", side_effect=lambda: clock[0]):
                result = run("Synthetic finalization deadline", FIXTURE, output, provider,
                             max_steps=16, max_tool_actions=24, max_seconds=120, on_event=on_event)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failure"]["type"], "TimeoutError")
            self.assertEqual((len(requests), result["tool_actions"]), (expected_requests, expected_actions))
            self.assertIsNone(result["answer"])
            self.assertFalse(result["investigation_complete"])

    def test_single_action_and_turn_budget_never_runs_nonterminal_tool(self):
        provider, requests = self.provider([batch(call(1, "inspect_schema", {}))])
        with patch("investigator.loop.Runtime.call") as execute:
            result = run("Synthetic one-slot budget", FIXTURE, self.root / "one", provider,
                         max_steps=1, max_tool_actions=1)
        execute.assert_not_called()
        self.assertEqual(result["tool_actions"], 0)
        self.assertEqual(len(requests), 1)
        self.assertEqual(self.budgets(requests)[0]["max_nonterminal_calls"], 0)
        self.assertEqual(result["failure"]["reason"]["code"], "finalization_tool_required")


if __name__ == "__main__":
    unittest.main()
