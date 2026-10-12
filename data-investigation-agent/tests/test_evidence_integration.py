"""Complete-package entry points and artifact checks; synthetic data, no network."""
from contextlib import redirect_stdout, redirect_stderr
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from investigator.cli import main
from investigator.evidence import load_answer_contract
from investigator.loop import run
from investigator.provenance import PUBLIC_SNAPSHOTS
from investigator.providers import ChatCompletionsProvider, DeepSeekProvider, selection
from investigator.recording import RecordedProvider, RecordedTransport
from investigator.replay import Replay, verify
from test_evidence_roles import (COUNT_CONTRACT, COUNT_SQL, RANK_CONTRACT, RANK_SQL,
                                 envelope, finish, fresh_bundle, independent_count_evaluation)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class EntryPointIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="answer-integration-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        guard = patch("socket.socket", side_effect=AssertionError("No network in offline checks"))
        guard.start()
        self.addCleanup(guard.stop)

    def cli(self, contract, output, responses=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["investigate", "--bundle", str(EXAMPLES / "simulation_bundle"),
                         "--responses", str(responses or EXAMPLES / "simulation_role_responses.json"),
                         "--answer-contract", str(contract), "--out", str(output)])
        return code, stdout.getvalue(), stderr.getvalue()

    def replay_and_notebook(self, output):
        for code in (None, "import json; n=json.load(open('investigation.ipynb')); ns={}; "
                           "[exec(''.join(c['source']), ns) for c in n['cells'] if c['cell_type']=='code']"):
            args = [sys.executable, "-I"] + (["-c", code] if code else ["replay.py"])
            result = subprocess.run(args, cwd=output, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_contract_runs_real_tools_and_exports_roles_with_independent_numbers(self):
        out = self.root / "cli"
        code, stdout, error = self.cli(EXAMPLES / "simulation_answer_contract.json", out)
        self.assertEqual(code, 0, error)
        self.assertIn("OFFLINE RECORDED RESPONSES", stdout)
        self.assertIn("答案证据：e006", stdout)
        report = json.loads((out / "report.json").read_text())
        self.assertEqual((report["status"], report["tool_actions"], report["live_request_attempts"]),
                         ("answered", 9, 0))
        self.assertEqual(report["answer"]["supporting_evidence_ids"], ["e002", "e003", "e007", "e008"])
        events = {e["evidence_id"]: e for e in map(json.loads, (out / "trace.jsonl").read_text().splitlines())}
        self.assertFalse(events["e004"]["result"]["ok"])
        expected = {}
        with (EXAMPLES / "simulation_bundle/simulation_runs.csv").open() as stream:
            for row in csv.DictReader(stream):
                if row["outcome"] in {"passed", "failed"}:
                    counts = expected.setdefault(row["period_key"], [0, 0])
                    counts[0] += row["outcome"] == "passed"
                    counts[1] += 1
        actual = events[report["answer"]["answer_evidence_id"]]["result"]["data"]["rows"]
        self.assertEqual(actual, [{"period_key": k, "passed_runs": v[0], "eligible_runs": v[1]}
                                  for k, v in sorted(expected.items())])
        self.assertIn('href="#e006"', (out / "report.html").read_text())
        self.assertIn("answer_contract.json", json.loads((out / "manifest.json").read_text())["artifacts"])
        self.replay_and_notebook(out)

    def test_invalid_cli_contract_fails_before_recording_or_output(self):
        for index, raw in enumerate([b"null", b"{", b"{}", b" " * 24001,
                                      json.dumps({**COUNT_CONTRACT, "expected_value": 2}).encode()]):
            with self.subTest(index=index):
                path = self.root / f"invalid-{index}.json"
                path.write_bytes(raw)
                out = self.root / f"rejected-{index}"
                with patch("investigator.recording.RecordedProvider", side_effect=AssertionError("Must not load recording")):
                    code, _, error = self.cli(path, out)
                self.assertEqual(code, 2)
                self.assertIn("SETUP ERROR", error)
                self.assertNotIn("AssertionError", error)
                self.assertFalse(out.exists())

    def test_contract_loader_rejects_links_in_file_or_parent(self):
        actual = self.root / "actual"
        actual.mkdir()
        path = actual / "contract.json"
        path.write_text(json.dumps(COUNT_CONTRACT))
        linked_file = self.root / "file.json"
        linked_file.symlink_to(path)
        linked_parent = self.root / "parent"
        linked_parent.symlink_to(actual, target_is_directory=True)
        for candidate in (linked_file, linked_parent / path.name):
            with self.subTest(path=candidate), self.assertRaisesRegex(ValueError, "Symlink"):
                load_answer_contract(candidate)

    def test_opted_in_legacy_recording_fails_visibly_and_replays(self):
        out = self.root / "legacy-recording-with-contract"
        code, _, _ = self.cli(EXAMPLES / "simulation_answer_contract.json", out,
                              EXAMPLES / "simulation_responses.json")
        self.assertEqual(code, 1)
        events = [json.loads(line) for line in (out / "trace.jsonl").read_text().splitlines()]
        rejected = next(e for e in events if e["tool"] == "finish")
        self.assertEqual(rejected["result"]["error"]["field"], "findings[0].evidence")
        self.assertIsNone(json.loads((out / "report.json").read_text())["answer"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(verify(out), 9)

    def test_failed_run_cannot_replay_as_legacy_after_both_manifest_bindings_removed(self):
        source = fresh_bundle(self.root)
        path = self.root / "unfinished.json"
        message = selection(1, "query", {"sql": COUNT_SQL}, "Only a query was recorded")
        path.write_text(json.dumps({"format_version": 1, "origin": "hand-authored",
                                    "responses": [envelope(message)]}))
        out = self.root / "unfinished"
        result = run("Offline incomplete run", source, out, RecordedProvider(path),
                     max_steps=3, max_tool_actions=12, answer_contract=COUNT_CONTRACT)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["answer"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(verify(out), 1)
        manifest = json.loads((out / "manifest.json").read_text())
        manifest.pop("answer_contract")
        manifest["artifacts"].pop("answer_contract.json")
        (out / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "silently become legacy"):
            Replay(out)

    def test_configured_client_preserves_contract_and_existing_request_controls(self):
        configured = runpy.run_path(str(EXAMPLES / "configured_client.py"))["investigate_with_client"]
        original = load_answer_contract(EXAMPLES / "simulation_answer_contract.json")
        frozen = copy.deepcopy(original)
        transport = RecordedTransport(EXAMPLES / "simulation_role_responses.json")
        requests = []

        def create(**request):
            requests.append(copy.deepcopy(request))
            original["columns"][0]["name"] = "caller_mutated_after_start"
            timeout = request.pop("timeout")
            self.assertGreater(timeout, 0)
            response = transport(request, timeout_seconds=timeout)
            return types.SimpleNamespace(model_dump=lambda: response.response)

        client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        out = self.root / "configured"
        with patch.object(ChatCompletionsProvider, "mode", "mock-scripted"):
            result = configured(client, model="offline-only", bundle=EXAMPLES / "simulation_bundle",
                                output=out, goal="Offline role integration", allow_data_sharing=True,
                                max_steps=12, max_output_tokens=1024, thinking="disabled",
                                answer_contract=original)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["answer_contract"], frozen)
        self.assertEqual(result["live_request_attempts"], 0)
        for request in requests:
            self.assertEqual(request["max_tokens"], 1024)
            self.assertEqual(request["extra_body"], {"thinking": {"type": "disabled"}})
            self.assertNotIn("caller_mutated_after_start", json.dumps(request))
        self.assertEqual(result["provider_activity"]["responses_received"], len(requests))
        self.replay_and_notebook(out)

    def test_legacy_transport_wrapper_passes_contract_and_existing_reference(self):
        wrapper = runpy.run_path(str(EXAMPLES / "parent_transport.py"))["investigate_with_existing_parent_transport"]
        recorded = RecordedTransport(EXAMPLES / "simulation_role_responses.json")
        references = []

        def transport(request, *, timeout_seconds, budget_reference):
            references.append(budget_reference)
            return recorded(request, timeout_seconds=timeout_seconds)

        with patch.object(DeepSeekProvider, "mode", "mock-scripted"):
            result = wrapper(transport, "offline-existing-reference", "offline-only",
                             EXAMPLES / "simulation_bundle", self.root / "parent", "Offline test",
                             answer_contract=load_answer_contract(EXAMPLES / "simulation_answer_contract.json"))
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["answer"]["answer_evidence_id"], "e006")
        self.assertEqual(references, ["offline-existing-reference"] * result["provider_requests"])

    def test_correct_and_wrong_shape_valid_numbers_are_separately_assessed(self):
        source = fresh_bundle(self.root)
        verdicts = []
        for label, sql in [("correct", COUNT_SQL), ("wrong", "SELECT 999 AS order_count")]:
            path = self.root / f"{label}.json"
            messages = [selection(1, "inspect_schema", {}, "Read supporting schema"),
                        selection(2, "query", {"sql": sql}, "Run selected answer query"),
                        selection(3, "finish", finish("e002", ["e001"]), "Return explicit roles")]
            path.write_text(json.dumps({"format_version": 1, "origin": "hand-authored",
                                        "responses": [envelope(m) for m in messages]}))
            out = self.root / label
            result = run("Count North orders with scans", source, out, RecordedProvider(path),
                         max_steps=3, max_tool_actions=12, answer_contract=COUNT_CONTRACT)
            self.assertEqual(result["status"], "answered")
            replay = Replay(out)
            for event in replay.events.values():
                replay.check(event)
            verdicts.append(independent_count_evaluation(source, result["answer"], replay.runtime.results)["numerically_correct"])
        self.assertEqual(verdicts, [True, False])

    def test_role_contract_composes_with_public_admission_and_explicit_nulls(self):
        source = fresh_bundle(self.root)
        declaration = {"type": "public-real", "dataset_id": "offline-role-admission-double",
                       "snapshot_id": "offline-role-admission-double-v1",
                       "source_url": "https://example.invalid/synthetic-test.csv",
                       "license_id": "CC0-1.0", "license_url": "https://example.invalid/license",
                       "retrieved_at": "2026-10-12T00:00:00Z", "upstream_sha256": "0" * 64,
                       "transformation": "Synthetic unit test double, not actual public data",
                       "attribution": "Original synthetic test authors",
                       "personal_data": False, "sensitive_data": False, "private_data": False}
        catalog = json.loads((source / "catalog.json").read_text())
        catalog.update(synthetic=False, provenance=declaration)
        (source / "catalog.json").write_text(json.dumps(catalog))
        registry = {declaration["snapshot_id"]: {"provenance": declaration,
                    "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()},
                    "review_reference": "Synthetic unit test only; not a public dataset approval"}}
        messages = [selection(1, "query", {"sql": RANK_SQL}, "Offline test ranking"),
                    selection(2, "finish", finish("e001"), "Select ranked rows")]
        path = self.root / "public-double-recording.json"
        path.write_text(json.dumps({"format_version": 1, "origin": "hand-authored",
                                    "responses": [envelope(m) for m in messages]}))
        out = self.root / "public-double"
        with patch.dict(PUBLIC_SNAPSHOTS, registry, clear=True):
            result = run("Synthetic admission path check", source, out, RecordedProvider(path),
                         max_steps=2, max_tool_actions=10, answer_contract=RANK_CONTRACT)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["provenance"]["type"], "public-real")
        event = json.loads((out / "trace.jsonl").read_text().splitlines()[0])
        self.assertIn(None, [row["category"] for row in event["result"]["data"]["rows"]])
        self.assertEqual(PUBLIC_SNAPSHOTS, {})
        self.replay_and_notebook(out)


if __name__ == "__main__":
    unittest.main()
