"""Offline public-interface tests with an original two-row probe and no diagnosis."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.bundle import prepare_bundle
from investigator.cli import main
from investigator.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).resolve().parent / "fixtures" / "public_metadata"


class PublicMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_public_shape_preserves_bytes_and_loads_types_without_network(self):
        original = {p.name: p.read_bytes() for p in PROBE.iterdir()}
        output = self.root / "inspection"
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            with contextlib.redirect_stdout(io.StringIO()):
                status = main(["inspect", "--fixture", str(PROBE), "--out", str(output)])
        self.assertEqual(status, 0)
        self.assertEqual(original, {p.name: p.read_bytes() for p in PROBE.iterdir()})
        for name, data in original.items():
            self.assertEqual((output / "input" / name).read_bytes(), data)
        runtime = Runtime(output / "input")
        catalog = runtime.call("catalog", "read_context", {"document": "catalog"})["data"]
        self.assertEqual(catalog, json.loads(original["catalog.json"]))
        self.assertNotIn("synthetic", catalog)  # No injected top-level marker or normalization.
        self.assertIsInstance(catalog["documents"], list)
        self.assertEqual(catalog["comparison"]["focus_period_id"], "2026-W40")
        for key, filename in (
            ("metric", "metric_definition.md"),
            ("dashboard", "dashboard_query.sql"),
            ("request", "request.txt"),
        ):
            observed = runtime.call(key, "read_context", {"document": key})
            self.assertEqual(observed["data"]["text"], original[filename].decode())
        schema = json.loads((output / "schema.json").read_text())["data"]["tables"]
        self.assertEqual(
            [(col["name"], col["type"]) for col in schema[0]["columns"]],
            [("record_id", "TEXT"), ("recorded_at_utc", "TEXT"),
             ("item_count", "INTEGER"), ("sample_value", "REAL")],
        )
        result = runtime.call("query", "query", {
            "sql": "SELECT * FROM observations ORDER BY record_id"})
        self.assertEqual(result["data"]["rows"], [
            {"record_id": "ROW-1", "recorded_at_utc": "2026-10-05T00:00:00Z",
             "item_count": 2, "sample_value": 1.5},
            {"record_id": "ROW-2", "recorded_at_utc": None,
             "item_count": 3, "sample_value": None},
        ])
        self.assertFalse((output / "report.json").exists())  # This is no Agent investigation.

    def test_existing_top_level_synthetic_fixture_remains_compatible(self):
        source = ROOT / "fixtures" / "delivery_slip"
        before = (source / "catalog.json").read_bytes()
        output = self.root / "legacy"
        prepare_bundle(source, output)
        self.assertEqual((output / "input" / "catalog.json").read_bytes(), before)
        self.assertEqual((source / "catalog.json").read_bytes(), before)
        schema = Runtime(output / "input").call("schema", "inspect_schema", {})
        self.assertTrue(schema["ok"])
        self.assertEqual(len(schema["data"]["tables"]), 5)

    def test_unrelated_authorship_and_matching_dual_declaration_are_accepted(self):
        for index, dual in enumerate((False, True)):
            source = self.root / f"source-{index}"
            shutil.copytree(PROBE, source)
            catalog = json.loads((source / "catalog.json").read_text())
            catalog["provenance"]["authorship"] = "Another explicit synthetic author"
            if dual:
                catalog["synthetic"] = True
            (source / "catalog.json").write_text(json.dumps(catalog))
            prepare_bundle(source, self.root / f"out-{index}")

    def test_missing_malformed_or_conflicting_declarations_are_rejected(self):
        valid = json.loads((PROBE / "catalog.json").read_text())["provenance"]
        invalid = [
            {},
            {"provenance": {}},
            {"provenance": {"authorship": valid["authorship"]}},
            {"provenance": None},
            {"provenance": []},
            {"provenance": "synthetic"},
        ]
        for key in ("type", "real_enterprise_data", "personal_data"):
            partial = dict(valid)
            del partial[key]
            invalid.append({"provenance": partial})
        for key in ("real_enterprise_data", "personal_data"):
            for value in (True, None, 0, "false"):
                invalid.append({"provenance": {**valid, key: value}})
        for value in (False, None, 0, 1, "true"):
            invalid.append({"synthetic": value, "provenance": valid})
        invalid.extend([
            {"synthetic": True, "provenance": {**valid, "type": "real"}},
            {"synthetic": True, "provenance": {**valid, "real_enterprise_data": True}},
            {"synthetic": True, "provenance": {**valid, "personal_data": True}},
        ])
        for index, declaration in enumerate(invalid):
            with self.subTest(declaration=declaration):
                source = self.root / f"source-{index}"
                shutil.copytree(PROBE, source)
                catalog = json.loads((source / "catalog.json").read_text())
                del catalog["provenance"]
                catalog.update(declaration)
                (source / "catalog.json").write_text(json.dumps(catalog))
                output = self.root / f"out-{index}"
                with self.assertRaises(ValueError):
                    prepare_bundle(source, output)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
