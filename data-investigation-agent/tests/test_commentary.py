"""Synthetic length-boundary fixtures; no reconstruction of the rejected live commentary."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.loop import MAX_CONTEXT_BYTES, NOTE_TRUNCATION_MARKER, normalize, run
from investigator.providers import DeepSeekProvider, selection

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "delivery_slip"
PRIVATE = "COMMENTARY-PRIVATE-REASONING-CANARY"
TAIL = "COMMENTARY-PUBLIC-TAIL-CANARY"


def commentary(length, character="x"):
    return character * (length - len(TAIL)) + TAIL


def query_batch(content, first_id=1):
    calls = []
    for number in range(first_id, first_id + 4):
        call = selection(number, "query", {}, "")["tool_calls"][0]
        # Deliberate whitespace and a JSON escape must survive feedback byte-for-byte.
        call["function"]["arguments"] = ' { "sql" : "SELECT COUNT(*) AS \\u006e FROM orders" } '
        calls.append(call)
    return {"role": "assistant", "content": content, "tool_calls": calls,
            "reasoning_content": PRIVATE}


class CommentaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        network = patch("socket.socket", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def provider(self, choose):
        requests = []

        def transport(payload, **kwargs):
            requests.append(copy.deepcopy(payload))
            return {"choices": [{"message": choose(len(requests), payload["messages"]),
                                  "finish_reason": "tool_calls"}]}

        provider = DeepSeekProvider(transport, model="offline-stub", parent_budget_reference="test-only")
        provider.mode = "mock-scripted"
        provider.label = "SCRIPTED commentary boundary fixture; no model API"
        return provider, requests

    def events(self, output):
        return [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]

    def test_300_301_319_and_long_notes_execute_with_exact_feedback_and_bounded_storage(self):
        for length, character in [(300, "x"), (301, "x"), (319, "x"), (100000, "x"), (65000, "测")]:
            with self.subTest(length=length, character=character):
                note = commentary(length, character)
                message = query_batch(note)
                original = copy.deepcopy(message)

                def choose(turn, messages):
                    if turn == 1:
                        # The parent's prevalidation uses the same API, without a length rejection.
                        clean, parsed = normalize(message)
                        self.assertEqual(clean["content"], note)
                        self.assertEqual(clean["tool_calls"], original["tool_calls"])
                        self.assertEqual(len(parsed), 4)
                        return message
                    self.assertEqual(turn, 2)
                    assistant = messages[-5]
                    self.assertEqual(assistant["content"], note)
                    self.assertEqual(assistant["tool_calls"], original["tool_calls"])
                    self.assertNotIn("reasoning_content", assistant)
                    self.assertEqual([m["tool_call_id"] for m in messages[-4:]],
                                     [call["id"] for call in original["tool_calls"]])
                    self.assertTrue(all(json.loads(m["content"])["data"]["rows"] == [{"n": 42}]
                                        for m in messages[-4:]))
                    self.assertLessEqual(len(json.dumps(messages, ensure_ascii=False).encode()),
                                         MAX_CONTEXT_BYTES)
                    return selection(5, "finish", {
                        "status": "answered", "summary": "Synthetic count verified",
                        "findings": [{"text": "42 development orders", "evidence": ["e001"]}],
                        "questions": [],
                    }, "Done")

                provider, requests = self.provider(choose)
                output = self.root / f"accepted-{length}"
                result = run("Offline commentary test", FIXTURE, output, provider,
                             max_steps=2, max_tool_actions=5)
                self.assertEqual(result["status"], "answered")
                self.assertEqual(result["tool_actions"], 5)
                self.assertEqual(len(requests), 2)
                self.assertEqual(message, original)
                for event in self.events(output)[:4]:
                    self.assertLessEqual(len(event["public_note"]), 300)
                    self.assertEqual(event["public_note_original_characters"], length)
                    self.assertEqual(event["public_note_truncated"], length > 300)
                    self.assertEqual(event["input"], {"sql": "SELECT COUNT(*) AS n FROM orders"})
                    if length > 300:
                        self.assertTrue(event["public_note"].endswith(NOTE_TRUNCATION_MARKER))
                    else:
                        self.assertEqual(event["public_note"], note)
                # Commentary is stored only as the display note and bounded structural metadata.
                for artifact in output.rglob("*"):
                    if artifact.is_file():
                        contents = artifact.read_bytes()
                        self.assertNotIn(PRIVATE.encode(), contents)
                        if length > 300:
                            self.assertNotIn(TAIL.encode(), contents)
                for filename in ["trace.jsonl", "report.html", "investigation.ipynb",
                                 "response_diagnostics.jsonl"]:
                    self.assertLess((output / filename).stat().st_size, 25000)

    def test_over_context_content_stops_before_any_tool_without_raw_text_storage(self):
        for index, note in enumerate([commentary(2000000), commentary(90000, "测"),
                                      commentary(130000, "\\")]):
            with self.subTest(index=index):
                provider, requests = self.provider(lambda *_: query_batch(note))
                output = self.root / f"oversized-{index}"
                with patch("investigator.loop.Runtime.call") as execute:
                    result = run("Actual context limit", FIXTURE, output, provider,
                                 max_steps=2, max_tool_actions=5)
                execute.assert_not_called()
                self.assertEqual(result["tool_actions"], 0)
                self.assertEqual(len(requests), 1)
                self.assertEqual(result["failure"]["phase"], "run_limits")
                self.assertIn("Context exceeds 250000 bytes", result["failure"]["message"])
                self.assertNotEqual(result["failure"]["type"], "InvalidResponse")
                self.assertEqual([e["tool"] for e in self.events(output)], ["run_error"])
                for name in ["trace.jsonl", "response_diagnostics.jsonl", "report.html"]:
                    self.assertLess((output / name).stat().st_size, 16000)
                    self.assertNotIn(TAIL, (output / name).read_text())
                    self.assertNotIn(PRIVATE, (output / name).read_text())

    def test_full_prior_commentary_counts_toward_cumulative_context_limit(self):
        first = query_batch(commentary(120000))
        second = query_batch(commentary(130000), first_id=5)

        def choose(turn, messages):
            if turn == 1:
                return first
            self.assertEqual(turn, 2)
            self.assertEqual(messages[-5]["content"], first["content"])
            return second

        provider, requests = self.provider(choose)
        output = self.root / "cumulative"
        result = run("Cumulative context limit", FIXTURE, output, provider,
                     max_steps=3, max_tool_actions=9)
        self.assertEqual(result["tool_actions"], 4)
        self.assertEqual(len(requests), 2)
        self.assertEqual(result["failure"]["phase"], "run_limits")
        self.assertIn("Context exceeds", result["failure"]["message"])
        self.assertEqual([e.get("tool_call_id") for e in self.events(output)],
                         ["call_1", "call_2", "call_3", "call_4", None])

    def test_commentary_change_does_not_relax_type_encoding_or_tool_schema_validation(self):
        for index, content in enumerate([False, 0, [], {"text": PRIVATE}, "\ud800"]):
            with self.subTest(content_type=type(content).__name__, index=index):
                provider, _ = self.provider(lambda *_: query_batch(content))
                with patch("investigator.loop.Runtime.call") as execute:
                    result = run("Invalid content", FIXTURE, self.root / f"invalid-{index}", provider,
                                 max_steps=1, max_tool_actions=4)
                execute.assert_not_called()
                self.assertEqual(result["failure"]["reason"]["code"], "content_invalid")
        message = query_batch(commentary(319))
        message["tool_calls"][3]["function"]["arguments"] = '{"unexpected": true}'
        provider, _ = self.provider(lambda *_: message)
        with patch("investigator.loop.Runtime.call") as execute:
            result = run("Invalid batch schema", FIXTURE, self.root / "schema", provider,
                         max_steps=1, max_tool_actions=4)
        execute.assert_not_called()
        self.assertEqual(result["failure"]["reason"],
                         {"code": "arguments_schema_invalid", "field": "tool_calls[3].function.arguments"})


if __name__ == "__main__":
    unittest.main()
