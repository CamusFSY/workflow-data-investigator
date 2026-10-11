"""Original unrelated-domain synthetic input; real SQL/exports, fixed offline responses."""
import contextlib
import copy
import csv
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.bundle import validate_bundle
from investigator.cli import main
from investigator.loop import run
from investigator.providers import selection
from investigator.recording import RecordedProvider
from investigator.replay import verify

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "examples/simulation_bundle"
RESPONSES = ROOT / "examples/simulation_responses.json"


class CustomBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_validation_has_no_provider_or_persistent_output_and_does_not_relabel_data(self):
        original = {p.name: p.read_bytes() for p in BUNDLE.iterdir()}
        code, out, err = self.invoke("validate", "--bundle", str(BUNDLE))
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertEqual(report["provider_calls"], 0)
        self.assertEqual(report["tables"][0]["name"], "simulation_runs")
        self.assertEqual(report["tables"][0]["rows"], 14)
        self.assertIn("authority", report["scope"])
        self.assertEqual(original, {p.name: p.read_bytes() for p in BUNDLE.iterdir()})
        source = self.root / "not-synthetic"
        shutil.copytree(BUNDLE, source)
        catalog = json.loads((source / "catalog.json").read_text())
        catalog["synthetic"] = False
        (source / "catalog.json").write_text(json.dumps(catalog))
        code, out, _ = self.invoke("validate", "--bundle", str(source))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["status"], "invalid")
        self.assertFalse(json.loads((source / "catalog.json").read_text())["synthetic"])

    def test_numeric_and_structural_errors_identify_file_row_column_without_cell_value(self):
        source = self.root / "numbers"
        shutil.copytree(BUNDLE, source)
        catalog = json.loads((source / "catalog.json").read_text())
        catalog["tables"][0]["columns"][0]["type"] = "INTEGER"
        (source / "catalog.json").write_text(json.dumps(catalog))
        code, out, _ = self.invoke("validate", "--bundle", str(source))
        self.assertEqual(code, 2)
        error = json.loads(out)["error"]["message"]
        self.assertIn("simulation_runs.csv, row 2, column run_id", error)
        self.assertNotIn("before-1", error)
        (source / "simulation_runs.csv").write_text("")
        self.assertEqual(self.invoke("validate", "--bundle", str(source))[0], 2)
        catalog["tables"] = [None]
        (source / "catalog.json").write_text(json.dumps(catalog))
        with self.assertRaisesRegex(ValueError, "object with a name"):
            validate_bundle(source)

    def test_custom_data_error_feedback_analysis_export_replay_and_changed_counts(self):
        outcomes = []
        for variant in ("original", "changed"):
            source = self.root / variant
            shutil.copytree(BUNDLE, source)
            if variant == "changed":
                with (source / "simulation_runs.csv").open(newline="") as stream:
                    rows = list(csv.DictReader(stream))
                next(row for row in rows if row["run_id"] == "after-3")["outcome"] = "failed"
                with (source / "simulation_runs.csv").open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
            output = self.root / (variant + "-output")
            code, stdout, stderr = self.invoke("investigate", "--bundle", str(source),
                "--responses", str(RESPONSES), "--out", str(output))
            self.assertEqual(code, 0, stderr)
            self.assertIn("OFFLINE RECORDED RESPONSES", stdout)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["mode"], "offline-recorded")
            self.assertEqual(report["live_calls"], 0)
            self.assertEqual(report["live_request_attempts"], 0)
            self.assertEqual(report["provider_activity"]["reported_not_dispatched"], 7)
            events = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
            self.assertFalse(events[3]["result"]["ok"])
            self.assertIn("reporting_week", events[3]["result"]["error"]["message"])
            self.assertEqual(events[4]["tool"], "inspect_schema")
            self.assertEqual(events[4]["decision_after_evidence"], "e004")
            self.assertIn("period_key", events[5]["input"]["sql"])
            self.assertEqual(verify(output), 9)
            outcomes.append(events[6]["result"]["data"])
            snapshot = (output / "manifest.json").read_bytes()
            self.assertEqual(self.invoke("investigate", "--bundle", str(source),
                "--responses", str(RESPONSES), "--out", str(output))[0], 2)
            self.assertEqual((output / "manifest.json").read_bytes(), snapshot)
        self.assertEqual(outcomes[0]["current"]["successes"], 3)
        self.assertEqual(outcomes[1]["current"]["successes"], 2)
        self.assertNotEqual(outcomes[0]["delta_percentage_points"], outcomes[1]["delta_percentage_points"])

    def test_missing_authority_is_kept_open_by_the_provider_contract(self):
        source = self.root / "uncertain"
        shutil.copytree(BUNDLE, source)
        (source / "metric_definition.md").write_text("Synthetic example. The denominator's cancellation rule is unspecified.\n")
        bodies = [
            {"choices": [{"message": selection(1, "read_context", {"document": "metric"}, "Read the unresolved definition.")}]},
            {"choices": [{"message": selection(2, "finish", {
                "status": "needs_clarification", "summary": "A denominator decision is required.",
                "findings": [{"text": "The supplied definition does not specify cancellation eligibility.", "evidence": ["e001"]}],
                "questions": ["Should cancelled simulation runs be excluded or included in eligible_runs?"],
            }, "Ask a concrete question; no invented definition.")}]},
        ]
        path = self.root / "clarification-responses.json"
        path.write_text(json.dumps({"format_version": 1, "origin": "hand-authored", "responses": bodies}))
        result = run("Offline clarification contract example", source, self.root / "uncertain-result", RecordedProvider(path))
        self.assertEqual(result["status"], "needs_clarification")
        self.assertFalse(result["investigation_complete"])
        self.assertIsNone(result["clarifications"][0]["resolution"])
        self.assertEqual(verify(self.root / "uncertain-result"), 2)

    def test_exhausted_and_malformed_responses_preserve_partial_failure_artifacts(self):
        original = json.loads(RESPONSES.read_text())
        for kind in ("exhausted", "malformed"):
            recording = copy.deepcopy(original)
            recording["responses"] = recording["responses"][:1]
            if kind == "malformed":
                recording["responses"].append({"choices": []})
            path = self.root / (kind + ".json");path.write_text(json.dumps(recording))
            output = self.root / kind
            code, _, _ = self.invoke("investigate", "--bundle", str(BUNDLE), "--responses", str(path), "--out", str(output))
            self.assertEqual(code, 1)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["tool_actions"], 3)
            self.assertEqual(verify(output), 3)
            self.assertTrue((output / "response_diagnostics.jsonl").is_file())

    def test_numeric_range_and_finiteness_fail_with_a_useful_location(self):
        for kind, bad in [("INTEGER", str(2 ** 63)), ("REAL", "NaN")]:
            source = self.root / kind
            shutil.copytree(BUNDLE, source)
            catalog = json.loads((source / "catalog.json").read_text())
            catalog["tables"][0]["columns"][0]["type"] = kind
            (source / "catalog.json").write_text(json.dumps(catalog))
            with (source / "simulation_runs.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            for index, row in enumerate(rows):
                row["run_id"] = bad if index == 0 else str(index)
            with (source / "simulation_runs.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "row 2, column run_id") as caught:
                validate_bundle(source)
            self.assertNotIn(bad, str(caught.exception))

    def test_recording_shape_size_and_links_fail_before_output(self):
        original = json.loads(RESPONSES.read_text())
        variants = [[], {**original, "format_version": True}, {**original, "origin": {}},
                    {**original, "responses": []}, {**original, "responses": [None] * 41}]
        for index, body in enumerate(variants):
            path = self.root / f"invalid-{index}.json";path.write_text(json.dumps(body))
            output = self.root / f"invalid-{index}-out"
            code, _, _ = self.invoke("investigate", "--bundle", str(BUNDLE), "--responses", str(path), "--out", str(output))
            self.assertEqual(code, 2)
            self.assertFalse(output.exists())
        large = self.root / "large.json";large.write_bytes(b" " * (512 * 1024 + 1))
        linked = self.root / "linked.json";linked.symlink_to(RESPONSES)
        for path in (large, linked):
            with self.assertRaisesRegex(ValueError, "Unsafe or oversized"):
                RecordedProvider(path)


if __name__ == "__main__":
    unittest.main()
