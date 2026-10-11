"""Locally authored, scripted protocol regressions; no model or independent-case answers."""
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.bundle import prepare_bundle
from investigator.loop import normalize, run
from investigator.protocol import InvalidResponse
from investigator.providers import selection
from investigator.replay import verify
from investigator.runtime import Runtime

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "missing_definition"
QUESTIONS = ["Which weekly grouping timestamp is approved?", "Which denominator is approved?",
             "How should unfinished records be counted?", "Which metric version is approved?"]
SUMMARY = "Synthetic fixture record count under the proposed interpretation."


def answer(status="answered", questions=(), conditions=(), refs=("e001",)):
    return {"status": status, "summary": SUMMARY,
            "findings": [{"text": "The synthetic table contains 42 records.", "evidence": list(refs)}],
            "questions": list(questions), "conditions": list(conditions)}


def resolution(qid="q001", kind="user"):
    return {"question_id": qid, "answer": "Synthetic verified answer to " + qid,
            "source_kind": kind, "source_reference": "local-test-confirmation/" + qid}


def response(number, name, args):
    return selection(number, name, args, "SCRIPTED clarification contract check")


class ScriptedResponses:
    mode = "mock-scripted"
    label = "SCRIPTED local clarification regression; no model invocation"

    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def next(self, messages, tools, timeout):
        self.requests.append(copy.deepcopy(messages))
        return copy.deepcopy(self.responses[len(self.requests) - 1])


class ClarificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        network = patch("socket.socket", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def runtime(self):
        output = self.root / "runtime"
        prepare_bundle(FIXTURE, output)
        runtime = Runtime(output / "input")
        result = runtime.call("e001", "query", {"sql": "SELECT COUNT(*) AS n FROM orders"})
        self.assertEqual(result["data"]["rows"], [{"n": 42}])
        return runtime

    def provider(self, *finishes):
        return ScriptedResponses([
            response(1, "query", {"sql": "SELECT COUNT(*) AS n FROM orders"}),
            *[response(i + 2, "finish", args) for i, args in enumerate(finishes)],
        ])

    def events(self, output):
        return [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]

    def replay(self, output, actions):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(output), actions)

    def test_deleting_questions_or_new_sql_cannot_clear_blockers(self):
        runtime = self.runtime()
        original = answer(questions=QUESTIONS)
        result = runtime.call("e002", "finish", original)
        self.assertFalse(result["ok"])
        self.assertIn("conditional", result["error"]["message"])
        self.assertEqual([q["id"] for q in result["clarifications"]], ["q001", "q002", "q003", "q004"])
        state = runtime.clarification_state()
        retry = copy.deepcopy(original)
        retry["questions"] = []  # Same summary, findings and refs: only questions change.
        self.assertFalse(runtime.call("e003", "finish", retry)["ok"])
        self.assertEqual(runtime.clarification_state(), state)
        self.assertTrue(runtime.call("e004", "query", {"sql": "SELECT COUNT(*) AS n FROM orders"})["ok"])
        self.assertTrue(runtime.call("e005", "read_context", {"document": "metric"})["ok"])
        retry["findings"][0]["evidence"] += ["e004", "e005"]
        self.assertFalse(runtime.call("e006", "finish", retry)["ok"])
        self.assertEqual(runtime.open_questions(), QUESTIONS)
        self.assertIsNone(runtime.finished)

    def test_needs_clarification_carries_omitted_questions_and_replays(self):
        provider = self.provider(answer(questions=QUESTIONS), answer("needs_clarification"))
        seen = []

        def unresolved(state):
            seen.append(copy.deepcopy(state))
            state.clear()  # Callback receives a copy, not mutable runtime state.
            return None

        output = self.root / "clarify"
        outcome = run("Synthetic clarification test", FIXTURE, output, provider,
                      max_steps=3, max_tool_actions=8, clarification_resolver=unresolved)
        self.assertEqual(outcome["status"], "needs_clarification")
        self.assertEqual(outcome["answer"]["questions"], QUESTIONS)
        self.assertFalse(outcome["investigation_complete"])
        self.assertEqual(len(seen), 1)
        self.assertEqual(outcome["live_calls"], 0)
        self.replay(output, 3)

    def test_conditional_requires_conditions_and_measured_evidence(self):
        runtime = self.runtime()
        for i, conditions in enumerate(([], ["   "])):
            self.assertFalse(runtime.call(f"missing{i}", "finish",
                answer("conditional", questions=QUESTIONS, conditions=conditions))["ok"])
        self.assertTrue(runtime.call("doc", "read_context", {"document": "metric"})["ok"])
        self.assertFalse(runtime.call("unmeasured", "finish", answer(
            "conditional", conditions=["Assume all records are eligible."], refs=["doc"]))["ok"])
        self.assertIsNone(runtime.finished)

    def test_conditional_report_is_qualified_before_claims_and_notebook_replays(self):
        conditions = ["Assume the table count is the required denominator."]
        provider = self.provider(answer(questions=QUESTIONS),
                                 answer("conditional", conditions=conditions))
        output = self.root / "conditional"
        outcome = run("Synthetic conditional test", FIXTURE, output, provider, max_steps=3, max_tool_actions=8)
        self.assertEqual(outcome["status"], "conditional")
        self.assertFalse(outcome["investigation_complete"])
        self.assertEqual(outcome["answer"]["questions"], QUESTIONS)
        self.assertEqual(outcome["answer"]["conditions"], conditions)
        report = (output / "report.html").read_text()
        self.assertLess(report.index("条件性结果"), report.index(SUMMARY))
        self.assertLess(report.index(conditions[0]), report.index(SUMMARY))
        self.assertLess(report.index(QUESTIONS[0]), report.index(SUMMARY))
        notebook = json.loads((output / "investigation.ipynb").read_text())
        first = "".join(notebook["cells"][0]["source"])
        self.assertIn("调查完成：否", first)
        self.assertIn("条件性结果", first)
        self.assertTrue(all(q in first for q in QUESTIONS))
        self.replay(output, 3)
        self.execute_notebook(output)

    def execute_notebook(self, output):
        result = subprocess.run([sys.executable, "-I", "-c",
            "import json\nbook=json.load(open('investigation.ipynb'))\n"
            "for cell in book['cells']:\n"
            " if cell['cell_type']=='code': exec(''.join(cell['source']))\n"],
            cwd=output, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_unconditional_answer_cannot_drop_its_conditions_either(self):
        runtime = self.runtime()
        self.assertFalse(runtime.call("e002", "finish", answer(
            conditions=["Every record belongs in the approved denominator.", "  "]))["ok"])
        self.assertEqual(len(runtime.open_conditions()), 1)
        self.assertFalse(runtime.call("e003", "finish", answer())["ok"])

    def test_other_finish_errors_do_not_discard_nonblank_questions(self):
        runtime = self.runtime()
        invalid = answer(questions=[QUESTIONS[0], "  "], refs=["unavailable"])
        result = runtime.call("e002", "finish", invalid)
        self.assertFalse(result["ok"])
        self.assertEqual(runtime.open_questions(), QUESTIONS[:1])
        self.assertFalse(runtime.call("e003", "finish", answer())["ok"])

    def test_blank_question_does_not_discard_real_assumption_before_retry(self):
        runtime = self.runtime()
        condition = "Every record belongs in the approved denominator."
        result = runtime.call("e002", "finish", answer(questions=[" "], conditions=[condition]))
        self.assertFalse(result["ok"])
        self.assertEqual(runtime.open_conditions(), [condition])
        self.assertEqual(runtime.clarification_state()[0]["kind"], "assumption")
        self.assertFalse(runtime.call("e003", "finish", answer())["ok"])
        conditional = runtime.call("e004", "finish", answer("conditional"))
        self.assertTrue(conditional["ok"])
        self.assertEqual(conditional["data"]["conditions"], [condition])

    def test_rejected_conditional_cannot_drop_assumptions_without_authority(self):
        condition = "Every record belongs in the approved denominator."
        provider = self.provider(answer("conditional", conditions=[condition], refs=["missing"]),
                                 answer(), answer(refs=["e001", "clarify-003"]))
        calls = []

        def resolve(state):
            calls.append(state)
            return None if len(calls) == 1 else [resolution("q001", "authority")]

        output = self.root / "conditional-resolution"
        outcome = run("Synthetic rejected conditional", FIXTURE, output, provider,
                      max_steps=4, max_tool_actions=8, clarification_resolver=resolve)
        self.assertEqual(outcome["status"], "answered")
        self.assertEqual(outcome["answer"]["conditions"], [])
        self.assertEqual([state[0]["question"] for state in calls], [condition, condition])
        self.assertTrue(all(state[0]["resolution"] is None for state in calls))
        self.assertEqual([e["evidence_id"] for e in self.events(output) if not e["result"]["ok"]],
                         ["e002", "e003"])
        self.replay(output, 4)
        self.execute_notebook(output)

    def test_resolved_twenty_then_new_blocker_overflow_latches_against_deletion(self):
        runtime = self.runtime()
        runtime.call("e002", "finish", answer(questions=[f"Question {i}?" for i in range(20)]))
        runtime.apply_clarifications("all-resolved", [resolution(f"q{i:03d}") for i in range(1, 21)])
        self.assertEqual(runtime.open_blockers(), [])
        state = runtime.clarification_state()
        failed = runtime.call("e003", "finish", answer(questions=["A new blocker?"]))
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["clarification_block"]["raised_at"], "e003")
        for i, status in enumerate(("answered", "conditional", "needs_clarification")):
            self.assertFalse(runtime.call(f"retry-{i}", "finish", answer(status))["ok"])
        self.assertEqual(runtime.clarification_state(), state)
        self.assertIsNone(runtime.finished)

    def test_overflow_stops_loop_and_exports_latched_failure_for_replay(self):
        provider = self.provider(answer(questions=[f"Question {i}?" for i in range(20)]),
                                 answer(questions=["A new blocker?"]), answer())
        output = self.root / "overflow"
        result = run("Synthetic capacity test", FIXTURE, output, provider, max_steps=4, max_tool_actions=8,
                     clarification_resolver=lambda state: [resolution(q["id"]) for q in state])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure"]["phase"], "clarification_state")
        self.assertEqual(result["provider_requests"], 3)
        self.assertEqual(result["clarification_block"]["raised_at"], "e003")
        self.assertTrue(all(q["resolution"] is not None for q in result["clarifications"]))
        self.assertIn("容量已满", (output / "report.html").read_text())
        self.replay(output, 3)

    def test_malformed_question_or_assumption_fields_remain_schema_errors(self):
        runtime = self.runtime()
        for i, change in enumerate(({"questions": [None]}, {"conditions": "assumption"},
                                    {"conditions": [{"text": "assumption"}]})):
            args = {**answer(), **change}
            with self.assertRaises(InvalidResponse):
                normalize(response(i + 2, "finish", args))
            self.assertFalse(runtime.call(f"invalid-{i}", "finish", args)["ok"])
            self.assertEqual(runtime.clarification_state(), [])
            self.assertIsNone(runtime.clarification_block)

    def test_partial_user_reply_then_authority_resolution_allow_answer_and_replay(self):
        provider = self.provider(answer(questions=QUESTIONS[:2]), answer(),
                                 answer(refs=["e001", "clarify-002", "clarify-003"]))
        calls = []

        def resolve(state):
            calls.append(copy.deepcopy(state))
            if len(calls) == 1:
                return [resolution("q001", "user")]
            self.assertIsNotNone(state[0]["resolution"])
            self.assertIsNone(state[1]["resolution"])
            return [resolution("q002", "authority")]

        output = self.root / "resolved"
        outcome = run("Synthetic resolution test", FIXTURE, output, provider,
                      max_steps=4, max_tool_actions=8, clarification_resolver=resolve)
        self.assertEqual(outcome["status"], "answered")
        self.assertTrue(outcome["investigation_complete"])
        self.assertEqual(outcome["answer"]["questions"], [])
        self.assertEqual(outcome["tool_actions"], 4)
        self.assertEqual(outcome["provider_requests"], 4)
        self.assertEqual(outcome["live_calls"], 0)
        self.assertEqual(len(calls), 2)
        events = self.events(output)
        external = [e for e in events if e["tool"] == "external_clarification"]
        self.assertEqual(len(external), 2)
        self.assertTrue(all(e["source"] == "trusted_caller" and "tool_call_id" not in e for e in external))
        failed = [e for e in events if not e["result"]["ok"]]
        self.assertEqual([e["evidence_id"] for e in failed], ["e002", "e003"])
        self.assertIsNotNone(failed[1]["result"]["clarifications"][0]["resolution"])
        self.assertIsNone(failed[1]["result"]["clarifications"][1]["resolution"])
        self.assertEqual(provider.requests[2][-1]["role"], "user")
        self.assertIn("clarify-002", provider.requests[2][-1]["content"])
        self.assertEqual(provider.requests[3][-2]["role"], "tool")
        self.assertIn("clarify-003", provider.requests[3][-1]["content"])
        report = (output / "report.html").read_text()
        self.assertIn("local-test-confirmation/q002", report)
        self.assertIn('href="#clarify-003"', report)
        self.replay(output, 4)  # External provenance events are not counted as model actions.
        self.execute_notebook(output)

    def test_model_cannot_call_resolution_or_inject_it_into_finish(self):
        runtime = self.runtime()
        runtime.call("e002", "finish", answer(questions=QUESTIONS))
        for number, name, args in [
            (3, "external_clarification", {"resolutions": [resolution()]}),
            (4, "finish", {**answer(), "resolutions": [resolution()]}),
        ]:
            with self.assertRaises(InvalidResponse):
                normalize(response(number, name, args))
            self.assertFalse(runtime.call(f"e00{number}", name, args)["ok"])
        self.assertEqual(runtime.open_questions(), QUESTIONS)

    def test_invalid_external_resolution_is_atomic_and_bounded(self):
        runtime = self.runtime()
        runtime.call("e002", "finish", answer(questions=QUESTIONS))
        original = runtime.clarification_state()
        invalid = [[], [resolution("unknown")], [resolution(), resolution()],
                   [resolution(), resolution("q002", "model")],
                   [{**resolution(), "source_reference": "  "}],
                   [resolution(), {**resolution("q002"), "answer": "x" * 8193}],
                   [{**resolution(), "answer": "x" * 7000},
                    {**resolution("q002"), "answer": "y" * 7000}]]
        for i, values in enumerate(invalid):
            with self.subTest(i=i), self.assertRaises(ValueError):
                runtime.apply_clarifications(f"invalid-{i}", values)
            self.assertEqual(runtime.clarification_state(), original)
        runtime.apply_clarifications("clarify", [resolution()])
        with self.assertRaises(ValueError):
            runtime.apply_clarifications("second", [resolution()])
        with self.assertRaises(ValueError):
            runtime.apply_clarifications("clarify", [resolution("q002")])
        self.assertEqual(len(runtime.open_questions()), 3)

    def test_question_state_cannot_grow_beyond_limits(self):
        runtime = self.runtime()
        runtime.call("e002", "finish", answer(questions=[f"Question {i}?" for i in range(20)]))
        state = runtime.clarification_state()
        result = runtime.call("e003", "finish", answer(questions=["An additional question?"]))
        self.assertFalse(result["ok"])
        self.assertIn("20 questions", result["error"]["message"])
        self.assertEqual(runtime.clarification_state(), state)
        runtime.apply_clarifications("first", [{**resolution(), "answer": "x" * 7900}])
        runtime.apply_clarifications("second", [{**resolution("q002"), "answer": "y" * 7900}])
        state = runtime.clarification_state()
        with self.assertRaisesRegex(ValueError, "24000"):
            runtime.apply_clarifications("third", [{**resolution("q003"), "answer": "z" * 7900}])
        self.assertEqual(runtime.clarification_state(), state)

    def test_exhaustion_retains_rejected_questions_and_failed_report(self):
        provider = self.provider(answer(questions=QUESTIONS), answer())
        output = self.root / "exhausted"
        outcome = run("Synthetic deletion test", FIXTURE, output, provider, max_steps=3, max_tool_actions=8)
        self.assertEqual(outcome["status"], "failed")
        self.assertIsNone(outcome["answer"])
        self.assertFalse(outcome["investigation_complete"])
        self.assertEqual([q["question"] for q in outcome["clarifications"]], QUESTIONS)
        self.assertEqual(sum(not e["result"]["ok"] for e in self.events(output)), 3)
        report = (output / "report.html").read_text()
        self.assertIn("已声明的阻塞问题仍未解决", report)
        self.assertTrue(all(q in report for q in QUESTIONS))
        self.replay(output, 3)

    def test_external_failure_and_deadline_stay_visible_without_private_details(self):
        canary = "PRIVATE-RESOLVER-ERROR-CANARY"

        def failure(state):
            raise RuntimeError(canary)

        def slow(state):
            time.sleep(3)

        for index, resolver in enumerate((failure, slow)):
            output = self.root / f"resolver-failure-{index}"
            provider = self.provider(answer(questions=QUESTIONS), answer())
            result = run("Synthetic callback failure", FIXTURE, output, provider,
                         max_steps=3, max_tool_actions=8, max_seconds=1, clarification_resolver=resolver)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failure"]["phase"], "external_clarification")
            self.assertIn("redacted", result["failure"]["message"])
            self.assertEqual(result["provider_requests"], 2)
            self.assertTrue(all(q["resolution"] is None for q in result["clarifications"]))
            self.assertNotIn(canary, (output / "trace.jsonl").read_text())
            self.replay(output, 2)

    def test_external_input_shares_context_limit(self):
        provider = self.provider(answer(questions=QUESTIONS[:1]), answer())
        output = self.root / "context"
        with patch("investigator.loop.MAX_CONTEXT_BYTES", 10000):
            result = run("Synthetic callback context limit", FIXTURE, output, provider,
                         max_steps=3, max_tool_actions=8, clarification_resolver=lambda state: [
                             {**resolution(), "answer": "x" * 8000}])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure"]["phase"], "run_limits")
        self.assertIn("Context exceeds", result["failure"]["message"])
        self.assertEqual(result["provider_requests"], 2)
        self.assertEqual(result["tool_actions"], 2)
        self.assertTrue(any(e["tool"] == "external_clarification" for e in self.events(output)))
        self.replay(output, 2)


if __name__ == "__main__":
    unittest.main()
