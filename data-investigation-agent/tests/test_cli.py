"""User-facing error contracts; real artifact replay, no provider/API calls."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from investigator.cli import GOAL, main
from investigator.loop import run
from investigator.mock import ScriptedMock

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class CliTests(unittest.TestCase):
    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_missing_replay_input_has_actionable_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _, error = self.invoke(["replay", str(Path(directory) / "missing")])
        self.assertEqual(code, 2)
        self.assertIn("REPLAY INPUT ERROR", error)
        self.assertNotIn("Traceback", error)

    def test_tampered_bundle_is_a_failed_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "evidence"
            run(GOAL, FIXTURES / "missing_definition", out, ScriptedMock())
            code, stdout, _ = self.invoke(["replay", str(out)])
            self.assertEqual(code, 0)
            self.assertIn("3 tool results", stdout)
            catalog = out / "input" / "catalog.json"
            self.assertFalse(catalog.stat().st_mode & 0o222)
            # Simulate a trusted host deliberately changing its own temporary copy.
            # Normal imported inputs remain read-only.
            catalog.chmod(0o600)
            catalog.write_text("{}")
            code, _, error = self.invoke(["replay", str(out)])
            self.assertEqual(code, 1)
            self.assertIn("Input hash mismatch", error)
            self.assertNotIn("Traceback", error)

    def test_malformed_manifest_has_verification_error_without_traceback(self):
        manifests = [
            [], {"input": []}, {"input": {"files": []}},
            {"input": {"files": None}},
            {"input": {"files": {}}, "runtime": []},
            {"input": {"files": {}}, "runtime": {}, "artifacts": []},
            {"input": {"files": {"catalog.json": None}}, "runtime": {}, "artifacts": {}},
        ]
        for manifest in manifests:
            with self.subTest(manifest=manifest), tempfile.TemporaryDirectory() as directory:
                (Path(directory) / "manifest.json").write_text(json.dumps(manifest))
                code, _, error = self.invoke(["replay", directory])
                self.assertEqual(code, 1)
                self.assertIn("REPLAY VERIFICATION FAILED: Invalid manifest", error)
                self.assertNotIn("Traceback", error)

    def test_live_flag_stops_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "must-not-exist"
            code, _, error = self.invoke([
                "run", "--mode", "live", "--fixture", str(FIXTURES / "join_multiplier"),
                "--out", str(out),
            ])
            self.assertEqual(code, 2)
            self.assertIn("LIVE_TRANSPORT_REQUIRED", error)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
