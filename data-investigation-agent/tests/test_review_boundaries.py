"""Original synthetic boundary regressions. All providers are hand-authored offline doubles."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import html
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from investigator.artifact_format import MAX_ARTIFACT_BYTES, MAX_MANIFEST_BYTES, json_text, write_artifact
from investigator.bundle import prepare_bundle
from investigator.cli import main
from investigator.evidence import freeze_answer_contract
from investigator.loop import run
from investigator.providers import selection
from investigator.recording import RecordedProvider
from investigator.replay import Replay
from investigator.runtime import Runtime


CONTRACT = {"columns": [{"name": "n", "type": "integer"}], "min_rows": 1, "max_rows": 1}
QUERY = ("query", {"sql": "SELECT COUNT(*) AS n FROM probe"})
QUESTION = "Which approval defines the denominator?"
CONDITION = "All rows are eligible under the approved denominator."


def answer(*, roles=True):
    args = {"status": "answered", "summary": "Original synthetic probe count.",
            "findings": [{"text": "Recorded count query."}], "questions": []}
    if roles:
        args.update(answer_evidence_id="e001", supporting_evidence_ids=[])
    else:
        args["findings"][0]["evidence"] = ["e002"]
    return args


class ReviewBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="offline-review-boundaries-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.catalog = {"synthetic": True, "tables": [
            {"name": "probe", "file": "probe.csv", "columns": {"id": "INTEGER"}}]}
        (self.source / "probe.csv").write_text("id\n1\n")
        for name in ("request.txt", "metric_definition.md", "dashboard_query.sql"):
            (self.source / name).write_text("-- Original synthetic boundary probe.\n")
        self.write_catalog()

    def tearDown(self):
        self.temp.cleanup()

    def write_catalog(self):
        (self.source / "catalog.json").write_text(json_text(self.catalog))

    def provider(self, actions):
        path = self.root / "recording.json"
        path.write_text(json_text({"format_version": 1, "origin": "hand-authored", "responses": [
            {"id": f"offline-{index}", "model": "offline-boundary-probe", "usage": {
                "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
             "choices": [{"finish_reason": "tool_calls", "message": selection(
                 index + 1, name, args, "Hand-authored offline boundary probe")} ]}
            for index, (name, args) in enumerate(actions)]}))
        return RecordedProvider(path)

    def execute(self, label, actions, *, contract=CONTRACT, **kwargs):
        output = self.root / label
        result = run("Count synthetic records with approved scope.", self.source, output,
                     self.provider(actions), max_steps=len(actions), max_tool_actions=12,
                     answer_contract=contract, **kwargs)
        events = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
        return output, result, events

    def replay(self, output, *, notebook=False):
        command = [sys.executable, "-B", "replay.py"]
        if notebook:
            command = [sys.executable, "-B", "-c", "import json; "
                       "nb=json.load(open('investigation.ipynb')); ns={}; "
                       "[exec(''.join(c['source']),ns) for c in nb['cells'] if c['cell_type']=='code']"]
        actual = subprocess.run(command, cwd=output, text=True, capture_output=True, timeout=20)
        self.assertEqual(actual.returncode, 0, actual.stderr)

    def test_unrelated_structure_errors_cannot_delete_questions_or_conditions(self):
        for label in ("legacy-evidence", "unknown-contract", "missing-summary", "invalid-status"):
            with self.subTest(label=label):
                rejected = answer()
                rejected.update(questions=[QUESTION], conditions=[CONDITION])
                if label == "legacy-evidence":
                    rejected["findings"][0]["evidence"] = ["e001"]
                elif label == "unknown-contract":
                    rejected["answer_contract"] = {**CONTRACT, "max_rows": 200}
                elif label == "missing-summary":
                    del rejected["summary"]
                else:
                    rejected["status"] = "approved"
                output, result, events = self.execute(label, [QUERY, ("finish", rejected), ("finish", answer())])
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["failure"]["phase"], "finalization_window")
                self.assertEqual((result["provider_requests"], result["tool_actions"], result["live_calls"]), (3, 3, 0))
                self.assertFalse(events[1]["result"]["ok"])
                self.assertIn("field", events[1]["result"]["error"])
                self.assertEqual([q["question"] for q in events[1]["result"]["clarifications"]], [QUESTION, CONDITION])
                self.assertIn("Unresolved questions", events[2]["result"]["error"]["message"])
                self.assertEqual(events[1]["result"]["clarifications"], result["clarifications"])
                self.assertEqual(result["answer_contract"], freeze_answer_contract(CONTRACT))
                self.assertIsNone(result["answer"])
                self.replay(output)
                self.replay(output, notebook=True)

    def test_invalid_blocker_field_does_not_erase_independently_valid_field(self):
        for invalid in ("questions", "conditions"):
            with self.subTest(invalid=invalid):
                rejected = answer()
                rejected.update(questions=[QUESTION], conditions=[CONDITION])
                rejected[invalid] = [{"text": "Malformed field is not a blocker string"}]
                output, result, events = self.execute(invalid, [QUERY, ("finish", rejected), ("finish", answer())])
                self.assertEqual(events[1]["result"]["error"]["field"], f"{invalid}[0]")
                self.assertEqual(result["status"], "failed")
                self.assertEqual([q["question"] for q in result["clarifications"]],
                                 [CONDITION if invalid == "questions" else QUESTION])
                self.replay(output)

    def test_invalid_blocker_fields_are_rejected_without_coercion_or_state(self):
        invalid_values = (None, "question", [None], [{"text": QUESTION}], [QUESTION, 1],
                          [QUESTION] * 21, ["q" * 8193])
        for field in ("questions", "conditions"):
            for index, value in enumerate(invalid_values):
                with self.subTest(field=field, index=index):
                    rejected = {**answer(), field: value}
                    output, result, events = self.execute(f"bad-{field}-{index}",
                        [QUERY, ("finish", rejected), ("finish", answer())])
                    self.assertEqual(events[1]["result"]["error"]["code"], "finish_argument_type")
                    self.assertEqual(result["clarifications"], [])
                    self.assertEqual(result["status"], "answered")
                    self.replay(output)

    def test_structural_rejection_retains_capacity_latch(self):
        first = {**answer(), "questions": [f"Question {i}?" for i in range(20)], "unexpected": True}
        second = {**answer(), "conditions": [CONDITION], "unexpected": True}
        output, result, _ = self.execute("capacity", [QUERY, ("finish", first), ("finish", second), ("finish", answer())])
        self.assertEqual(result["failure"]["phase"], "clarification_state")
        self.assertEqual(result["clarification_block"]["raised_at"], "e003")
        self.assertEqual(result["provider_requests"], 3)
        self.assertEqual(len(result["clarifications"]), 20)
        self.replay(output)

    def test_oversized_finish_cannot_mutate_blocker_state(self):
        prepare_bundle(self.source, self.root / "prepared")
        runtime = Runtime(self.root / "prepared" / "input", answer_contract=CONTRACT)
        result = runtime.call("oversized", "finish", {
            **answer(), "questions": [QUESTION], "summary": "x" * 12000})
        self.assertFalse(result["ok"])
        self.assertIn("12 KiB", result["error"]["message"])
        self.assertEqual(runtime.clarification_state(), [])

    def test_retained_structural_error_question_can_be_resolved_by_trusted_caller(self):
        rejected = {**answer(), "questions": [QUESTION], "unexpected": True}
        states = []
        def resolve(state):
            states.append(copy.deepcopy(state))
            return [{"question_id": "q001", "answer": "All rows are eligible.", "source_kind": "user",
                     "source_reference": "Original synthetic test reply"}]
        output, result, _ = self.execute("resolved", [QUERY, ("finish", rejected), ("finish", answer())],
                                        clarification_resolver=resolve)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(states[0][0]["question"], QUESTION)
        self.assertEqual(result["answer"]["questions"], [])
        self.replay(output)

    def test_64_column_contract_is_executable_and_replayable(self):
        contract = {**CONTRACT, "columns": [{"name": f"c{i}", "type": "integer"} for i in range(64)]}
        output, result, events = self.execute("width-64", [("query", {
            "sql": "SELECT " + ",".join(f"{i} AS c{i}" for i in range(64))}), ("finish", answer())], contract=contract)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(len(events[0]["result"]["data"]["columns"]), 64)
        self.replay(output)

    def test_65_column_contract_rejected_before_provider_bundle_or_output(self):
        contract = {**CONTRACT, "columns": [{"name": f"c{i}", "type": "integer"} for i in range(65)]}
        output = self.root / "no-output"
        with patch("investigator.loop.provider_contract") as provider_check, patch("investigator.loop.prepare_bundle") as prepare:
            with self.assertRaisesRegex(ValueError, "1..64"):
                run("Task", self.root / "missing-bundle", output, object(), answer_contract=contract)
        provider_check.assert_not_called()
        prepare.assert_not_called()
        self.assertFalse(output.exists())
        path = self.root / "contract-65.json"
        path.write_text(json_text(contract))
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
            code = main(["investigate", "--bundle", str(self.root / "missing-bundle"),
                         "--responses", str(self.root / "missing-recording"), "--answer-contract", str(path), "--out", str(output)])
        self.assertEqual(code, 2)
        self.assertIn("1..64", error.getvalue())
        self.assertFalse(output.exists())

    def metadata_roundtrip(self, label, declaration):
        self.catalog["provenance"] = declaration
        self.write_catalog()
        self.assertLess((self.source / "catalog.json").stat().st_size, 65536)
        source_bytes = (self.source / "catalog.json").read_bytes()
        output, result, events = self.execute(label, [
            ("read_context", {"document": "catalog"}), QUERY, ("finish", answer(roles=False))], contract=None)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["live_calls"], 0)
        self.assertEqual(result["provenance"]["declaration"], declaration)
        self.assertEqual(events[0]["result"]["data"], self.catalog)
        self.assertEqual((output / "input" / "catalog.json").read_bytes(), source_bytes)
        manifest = json.loads((output / "manifest.json").read_bytes())
        self.assertEqual(manifest["input"]["provenance"]["declaration"], declaration)
        self.assertLess((output / "manifest.json").stat().st_size, MAX_MANIFEST_BYTES)
        for name in ("report.json", "report.html", "investigation.ipynb"):
            self.assertLess((output / name).stat().st_size, min(MAX_ARTIFACT_BYTES, 512 * 1024))
        notebook = json.loads((output / "investigation.ipynb").read_bytes())
        self.assertIn(json_text(result["provenance"]), "".join(notebook["cells"][0]["source"]))
        self.assertIn(json_text(result["provenance"]), html.unescape((output / "report.html").read_text()))
        self.assertEqual(Replay(output).provenance["declaration"], declaration)
        self.replay(output)
        self.replay(output, notebook=True)

    def test_shallow_array_metadata_exports_without_whitespace_expansion(self):
        self.metadata_roundtrip("shallow", {"metadata": [0] * 20000})

    def test_nested_array_metadata_exports_and_notebook_replays_within_original_limits(self):
        metadata = [0] * 25000
        for _ in range(180):
            metadata = [metadata]
        self.metadata_roundtrip("nested", {"metadata": metadata})

    def test_legacy_synthetic_list_and_dict_snapshot_ids_standalone_replay(self):
        for label, value in (("list", ["batch-a", "batch-b"]), ("dict", {"batch": "a"})):
            with self.subTest(label=label):
                self.metadata_roundtrip(label, {"snapshot_id": value})

    def test_artifact_writer_counts_utf8_bytes_and_rejects_before_write(self):
        path = self.root / "small.json"
        with self.assertRaisesRegex(ValueError, "replay limit"):
            write_artifact(path, "数" * 4, limit=10)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
