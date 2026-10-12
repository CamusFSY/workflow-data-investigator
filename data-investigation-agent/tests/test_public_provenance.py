"""Synthetic admission test doubles only; no real dataset or benchmark success claim."""
import contextlib
import copy
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.bundle import prepare_bundle, validate_bundle
from investigator.cli import main
from investigator.loop import run
from investigator.provenance import PUBLIC_SNAPSHOTS
from investigator.providers import selection
from investigator.recording import RecordedProvider
from investigator.replay import Replay, verify
from investigator.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "simulation_bundle"


class PublicProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "synthetic-admission-test-double"
        shutil.copytree(EXAMPLE, self.source)
        self.declaration = {
            "type": "public-real", "dataset_id": "offline-admission-test-double",
            "snapshot_id": "offline-admission-test-double-v1",
            "source_url": "https://example.invalid/synthetic-admission-test-double.csv",
            "license_id": "CC0-1.0", "license_url": "https://example.invalid/test-license",
            "retrieved_at": "2026-10-11T00:00:00Z", "upstream_sha256": "0" * 64,
            "transformation": "SYNTHETIC UNIT TEST DOUBLE, not actual public data or a benchmark.",
            "attribution": "Original synthetic unit test authors; no third-party real data.",
            "personal_data": False, "sensitive_data": False, "private_data": False,
        }
        self.catalog = json.loads((self.source / "catalog.json").read_text())
        self.catalog.update(synthetic=False, provenance=copy.deepcopy(self.declaration))
        self.write_catalog()

    def tearDown(self):
        self.temp.cleanup()

    def write_catalog(self):
        (self.source / "catalog.json").write_text(json.dumps(self.catalog), encoding="utf-8")

    def registry(self):
        return {self.declaration["snapshot_id"]: {
            "provenance": copy.deepcopy(self.catalog["provenance"]),
            "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()},
            "review_reference": "Synthetic unit-test-only registry, never a reviewed real dataset",
        }}

    def admitted(self):
        return patch.dict(PUBLIC_SNAPSHOTS, self.registry(), clear=True)

    def test_no_public_snapshot_is_enabled_by_default(self):
        self.assertEqual(PUBLIC_SNAPSHOTS, {})
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            prepare_bundle(self.source, self.root / "denied")
        self.assertFalse((self.root / "denied").exists())
        provider = type("Provider", (), {"mode": "mock-scripted", "label": "Never called",
                                        "next": lambda *a: self.fail("Provider must not run")})()
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            run("No public source is authorized", self.source, self.root / "denied-run", provider)
        self.assertFalse((self.root / "denied-run").exists())

    def test_admission_and_validation_preserve_original_bytes_and_full_provenance(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        with self.admitted(), patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            report = validate_bundle(self.source)
            imported = prepare_bundle(self.source, self.root / "loaded")
        self.assertFalse(report["synthetic"])
        self.assertEqual(report["provenance"], imported["provenance"])
        self.assertEqual(report["provenance"]["declaration"], self.declaration)
        self.assertEqual(report["tables"][0]["rows"], 14)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})
        self.assertEqual(before, {name: (self.root / "loaded/input" / name).read_bytes() for name in before})
        self.assertTrue(all(not p.stat().st_mode & 0o222 for p in (self.root / "loaded/input").iterdir()))

    def test_declaration_missing_fields_false_flags_and_conflicts_fail_before_output(self):
        original = copy.deepcopy(self.catalog)
        cases = []
        for key in self.declaration:
            changed = copy.deepcopy(original); del changed["provenance"][key]; cases.append(changed)
        for key in ("personal_data", "sensitive_data", "private_data"):
            for value in (True, 0, "false", None):
                changed = copy.deepcopy(original); changed["provenance"][key] = value; cases.append(changed)
        for key, value in (("source_url", "file:///etc/passwd"), ("source_url", "https://user:pass@example.invalid"),
                           ("license_url", "http://example.invalid"), ("license_id", ""),
                           ("upstream_sha256", "not-a-hash"), ("retrieved_at", "yesterday"),
                           ("transformation", ""), ("type", "real")):
            changed = copy.deepcopy(original); changed["provenance"][key] = value; cases.append(changed)
        for flag in (True, None, 0, "false"):
            changed = copy.deepcopy(original); changed["synthetic"] = flag; cases.append(changed)
        for i, catalog in enumerate(cases):
            with self.subTest(i=i):
                self.catalog = catalog; self.write_catalog()
                with self.admitted(), self.assertRaises(ValueError):
                    prepare_bundle(self.source, self.root / f"rejected-{i}")
                self.assertFalse((self.root / f"rejected-{i}").exists())

    def test_every_context_and_csv_file_is_pinned_and_cannot_self_allowlist(self):
        approved = self.registry()
        originals = {p.name: p.read_bytes() for p in self.source.iterdir()}
        for i, name in enumerate(originals):
            with self.subTest(name=name):
                (self.source / name).write_bytes(originals[name] + b"\n")
                with patch.dict(PUBLIC_SNAPSHOTS, approved, clear=True), self.assertRaisesRegex(ValueError, "SHA256"):
                    prepare_bundle(self.source, self.root / f"tampered-{i}")
                self.assertFalse((self.root / f"tampered-{i}").exists())
                (self.source / name).write_bytes(originals[name])
        self.catalog["provenance"]["source_url"] = "https://example.invalid/unreviewed-source"
        self.write_catalog()
        with patch.dict(PUBLIC_SNAPSHOTS, approved, clear=True), self.assertRaisesRegex(ValueError, "allowlist entry"):
            prepare_bundle(self.source, self.root / "spoofed")

    def test_public_trace_report_notebook_svg_and_standalone_replay_agree(self):
        seen = []
        class ObserveRecording(RecordedProvider):
            def next(self, messages, tools, timeout_seconds):
                seen.append(copy.deepcopy(messages))
                return super().next(messages, tools, timeout_seconds)
        output = self.root / "recorded-public-path-test"
        with self.admitted(), patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            result = run("Offline synthetic admission test only", self.source, output,
                         ObserveRecording(ROOT / "examples/simulation_responses.json"))
        self.assertFalse(result["synthetic"])
        self.assertEqual(result["mode"], "offline-recorded")
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["tool_actions"], 9)
        self.assertIn("PUBLIC REAL DATA", seen[0][0]["content"])
        self.assertNotIn("All data here are SYNTHETIC", seen[0][0]["content"])
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["input"]["provenance"], result["provenance"])
        self.assertIn("provenance.py", manifest["runtime"])
        for file in [output / "report.html", output / "investigation.ipynb", *output.glob("chart-*.svg")]:
            text = file.read_text()
            self.assertIn("PUBLIC REAL DATA", text)
            self.assertIn(self.declaration["snapshot_id"], text)
            self.assertIn(self.declaration["license_id"], text)
        events = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
        self.assertTrue(any(not e["result"]["ok"] for e in events))
        self.assertTrue(all(e["data_provenance"]["type"] == "public-real" for e in events))
        self.assertTrue(all(e["data_provenance"]["snapshot_id"] == self.declaration["snapshot_id"] for e in events))
        self.assertEqual(PUBLIC_SNAPSHOTS, {})  # Replay uses the frozen record, no global approval or network.
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(output), 9)
        replay = subprocess.run([sys.executable, "replay.py"], cwd=output, text=True, capture_output=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertIn("PUBLIC REAL DATA", replay.stdout)
        notebook = subprocess.run([sys.executable, "-c",
            "import json; n=json.load(open('investigation.ipynb')); ns={}; "
            "[exec(''.join(c['source']),ns) for c in n['cells'] if c['cell_type']=='code']"],
            cwd=output, text=True, capture_output=True)
        self.assertEqual(notebook.returncode, 0, notebook.stderr)
        # Changing a declaration in the unsigned manifest alone is detected.
        manifest["input"]["provenance"]["declaration"]["license_id"] = "CC-BY-4.0"
        (output / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            Replay(output)

    def test_inspect_and_recorded_cli_never_print_a_synthetic_banner_for_public_input(self):
        with self.admitted(), contextlib.redirect_stdout(io.StringIO()) as text:
            code = main(["inspect", "--bundle", str(self.source), "--out", str(self.root / "inspect")])
        self.assertEqual(code, 0)
        self.assertIn("PUBLIC REAL DATA", text.getvalue())
        self.assertNotIn("SYNTHETIC DATA", text.getvalue())
        with self.admitted(), contextlib.redirect_stdout(io.StringIO()) as text:
            code = main(["investigate", "--bundle", str(self.source), "--responses",
                         str(ROOT / "examples/simulation_responses.json"), "--out", str(self.root / "cli")])
        self.assertEqual(code, 0)
        self.assertIn("PUBLIC REAL DATA", text.getvalue())
        self.assertNotIn("SYNTHETIC DATA", text.getvalue())

    def test_continuous_values_stay_query_values_and_are_not_rounded_into_counts(self):
        with self.admitted():
            manifest = prepare_bundle(self.source, self.root / "continuous")
        runtime = Runtime(self.root / "continuous/input", provenance=manifest["provenance"])
        actual = runtime.call("q", "query", {"sql": "SELECT 'before' AS period, 31.1256 AS value, 100 AS total UNION ALL SELECT 'after', NULL, 100"})
        self.assertTrue(actual["ok"])
        self.assertEqual(actual["data"]["rows"][0]["value"], 31.1256)
        self.assertIsNone(actual["data"]["rows"][1]["value"])
        plotted = runtime.call("p", "plot", {"evidence_id": "q", "label": "period", "successes": "value", "total": "total"})
        self.assertFalse(plotted["ok"])
        self.assertIn("integer counts", plotted["error"]["message"])

    def test_large_valid_legacy_synthetic_provenance_remains_replayable(self):
        self.catalog.update(synthetic=True, provenance={"type": "synthetic", "personal_data": False,
            "real_enterprise_data": False, "authorship": "x" * 63900})
        self.write_catalog()
        self.assertLess((self.source / "catalog.json").stat().st_size, 65536)
        class Minimal:
            mode, label, count = "mock-scripted", "Offline legacy metadata boundary", 0
            def next(self, messages, tools, timeout_seconds):
                self.count += 1
                if self.count == 1:
                    return selection(1, "query", {"sql": "SELECT COUNT(*) AS n FROM simulation_runs"}, "Count rows")
                return selection(2, "finish", {"status": "answered", "summary": "Counted rows",
                    "findings": [{"text": "Actual row count", "evidence": ["e001"]}], "questions": []}, "Finish")
        output = self.root / "large-legacy"
        result = run("Offline metadata boundary", self.source, output, Minimal())
        self.assertTrue(result["synthetic"])
        self.assertGreater((output / "manifest.json").stat().st_size, 65536)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(output), 2)


if __name__ == "__main__":
    unittest.main()
