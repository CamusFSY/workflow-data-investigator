"""Original synthetic probes for explicit NULL/empty-string transport semantics."""
import contextlib
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.bundle import prepare_bundle
from investigator.loop import run
from investigator.providers import selection
from investigator.recording import RecordedProvider
from investigator.replay import verify
from investigator.runtime import Runtime


class CSVNullEncodingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "synthetic-source"
        self.source.mkdir()
        self.catalog = {"synthetic": True, "csv_null_encoding": "backslash-N", "tables": [{
            "name": "observations", "file": "observations.csv",
            "columns": {"id": "INTEGER", "label": "TEXT", "amount": "REAL"}}]}
        (self.source / "metric_definition.md").write_text(
            "SYNTHETIC transport probe. NULL means unknown; empty TEXT is a known empty value.\n")
        (self.source / "request.txt").write_text("Count missing and empty labels separately.\n")
        (self.source / "dashboard_query.sql").write_text("-- No dashboard supplied.\n")
        self.csv = 'id,label,amount\n1,,0\n2,\\N,\\N\n3,"\\N",1.25\n4,  ,2\n5,雪,-0.5\n'
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        (self.source / "catalog.json").write_text(json.dumps(self.catalog), encoding="utf-8")
        (self.source / "observations.csv").write_bytes(self.csv.encode("utf-8"))

    def test_explicit_marker_preserves_empty_text_types_whitespace_and_source_bytes(self):
        original = {p.name: p.read_bytes() for p in self.source.iterdir()}
        output = self.root / "imported"
        manifest = prepare_bundle(self.source, output)
        runtime = Runtime(output / "input")
        result = runtime.call("values", "query", {"sql":
            "SELECT id, label, amount, typeof(label) AS label_type, typeof(amount) AS amount_type "
            "FROM observations ORDER BY id"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["rows"], [
            {"id": 1, "label": "", "amount": 0.0, "label_type": "text", "amount_type": "real"},
            {"id": 2, "label": None, "amount": None, "label_type": "null", "amount_type": "null"},
            {"id": 3, "label": None, "amount": 1.25, "label_type": "null", "amount_type": "real"},
            {"id": 4, "label": "  ", "amount": 2.0, "label_type": "text", "amount_type": "real"},
            {"id": 5, "label": "雪", "amount": -0.5, "label_type": "text", "amount_type": "real"},
        ])
        self.assertIn("empty TEXT stays empty", manifest["import"])
        self.assertEqual(original, {p.name: p.read_bytes() for p in self.source.iterdir()})
        self.assertEqual(original, {name: (output / "input" / name).read_bytes() for name in original})
        self.assertTrue(all(not p.stat().st_mode & 0o222 for p in (output / "input").iterdir()))

    def test_default_and_explicit_legacy_mode_keep_empty_as_null_and_marker_as_text(self):
        self.csv = 'id,label,amount\n1,,\n2,\\N,3\n'
        for index, explicit in enumerate((False, True)):
            if explicit:
                self.catalog["csv_null_encoding"] = "empty"
            else:
                del self.catalog["csv_null_encoding"]
            self.write()
            output = self.root / f"legacy-{index}"
            manifest = prepare_bundle(self.source, output)
            with sqlite3.connect(f"file:{output / 'input/data.sqlite'}?mode=ro", uri=True) as conn:
                self.assertEqual(conn.execute("SELECT * FROM observations ORDER BY id").fetchall(),
                                 [(1, None, None), (2, r"\N", 3.0)])
            self.assertEqual(manifest["import"],
                             "Empty CSV cells become NULL; unspecified column types are TEXT.")

    def test_empty_numeric_is_rejected_in_explicit_mode_with_location_and_no_cell_echo(self):
        for index, (column, row) in enumerate((("id", ",valid,1"), ("amount", "1,valid,"))):
            self.csv = "id,label,amount\n" + row + "\n"
            self.write()
            output = self.root / f"invalid-number-{index}"
            with self.assertRaisesRegex(ValueError, f"row 2, column {column}") as caught:
                prepare_bundle(self.source, output)
            self.assertIn(r"literal \N for NULL", str(caught.exception))
            self.assertNotIn("valid", str(caught.exception).replace("Invalid", ""))
            self.assertTrue((output / "setup_error.txt").is_file())

    def test_unknown_mode_is_rejected_before_output_or_provider_dispatch(self):
        class NeverProvider:
            mode, label = "mock-scripted", "No provider may run for an invalid catalog"

            def next(self, *args):
                raise AssertionError("Provider dispatch is forbidden")

        for index, invalid in enumerate((None, True, 0, [], {}, "NULL", "\\N")):
            with self.subTest(invalid=invalid):
                self.catalog["csv_null_encoding"] = invalid
                self.write()
                output = self.root / f"invalid-mode-{index}"
                with self.assertRaisesRegex(ValueError, "csv_null_encoding"):
                    run("Offline invalid mode probe", self.source, output, NeverProvider())
                self.assertFalse(output.exists())

    def test_actual_error_query_and_null_counts_replay_in_exported_notebook(self):
        actions = [
            ("read_context", {"document": "metric"}, "Read the synthetic NULL convention."),
            ("read_context", {"document": "catalog"}, "Read the declared transport mode."),
            ("query", {"sql": "SELECT missing_label FROM observations"}, "Exercise a controlled SQL error."),
            ("inspect_schema", {}, "Inspect columns after the actual SQL error."),
            ("query", {"sql": "SELECT SUM(label IS NULL) AS missing_count, "
                       "SUM(label = '') AS empty_count, COUNT(*) AS row_count FROM observations"},
             "Use the actual column and count NULL separately from empty TEXT."),
            ("finish", {"status": "answered", "summary": "Offline synthetic transport probe completed.",
                        "findings": [{"text": "Two NULL labels and one empty TEXT among five rows.",
                                      "evidence": ["e005"]}], "questions": []},
             "Export the measured query evidence; no autonomous model was used."),
        ]
        bodies = [{"choices": [{"message": selection(i, name, args, note)}]}
                  for i, (name, args, note) in enumerate(actions, 1)]
        recording = self.root / "responses.json"
        recording.write_text(json.dumps({"format_version": 1, "origin": "hand-authored", "responses": bodies}))
        output = self.root / "recorded-result"
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            result = run("Count missing and empty labels separately", self.source, output,
                         RecordedProvider(recording), max_steps=8, max_tool_actions=12)
        self.assertEqual(result["mode"], "offline-recorded")
        self.assertEqual(result["status"], "answered")
        events = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
        self.assertEqual(len(events), 6)
        self.assertFalse(events[2]["result"]["ok"])
        self.assertIn("no such column", events[2]["result"]["error"]["message"])
        self.assertEqual(events[4]["result"]["data"]["rows"],
                         [{"missing_count": 2, "empty_count": 1, "row_count": 5}])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(output), 6)
        replay = subprocess.run([sys.executable, "replay.py"], cwd=output, capture_output=True, text=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        notebook = subprocess.run([sys.executable, "-c",
            "import json; n=json.load(open('investigation.ipynb')); ns={}; "
            "[exec(''.join(c['source']), ns) for c in n['cells'] if c['cell_type']=='code']"],
            cwd=output, capture_output=True, text=True)
        self.assertEqual(notebook.returncode, 0, notebook.stderr)


if __name__ == "__main__":
    unittest.main()
