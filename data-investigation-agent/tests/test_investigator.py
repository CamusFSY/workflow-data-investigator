import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from investigator.bundle import digest, prepare_bundle
from investigator.cli import GOAL, main
from investigator.loop import run
from investigator.mock import ScriptedMock
from investigator.providers import DeepSeekProvider, selection
from investigator.replay import Replay, verify
from investigator.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def events(path):
    return [json.loads(line) for line in (path / "trace.jsonl").read_text().splitlines()]


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def investigate(self, fixture, name="run", inject=False, **limits):
        path = self.root / name
        result = run(GOAL, FIXTURES / fixture, path, ScriptedMock(inject), **limits)
        return path, result

    def runtime(self):
        path = self.root / "tools"
        prepare_bundle(FIXTURES / "delivery_slip", path)
        return Runtime(path / "input")

    def test_duplicate_join_error_recovery_and_exact_offline_replay(self):
        path, result = self.investigate("join_multiplier", inject=True)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["live_calls"], 0)
        trace = events(path)
        failed = next(e for e in trace if not e["result"]["ok"])
        self.assertIn("no such column", failed["result"]["error"]["message"])
        index = trace.index(failed)
        self.assertEqual(trace[index + 1]["tool"], "inspect_schema")
        self.assertIn("promised_delivery_at_utc", trace[index + 2]["input"]["sql"])
        measured = [e["result"]["data"] for e in trace if e["tool"] == "analyze"]
        self.assertAlmostEqual(measured[0]["current"]["rate"], 18 / 26)
        self.assertEqual(measured[1]["delta_percentage_points"], 0)
        self.assertEqual(verify(path), 14)
        replay = subprocess.run([sys.executable, "-I", str(path / "replay.py")],
                                capture_output=True, text=True, check=False, cwd="/tmp")
        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertIn("14 tool results", replay.stdout)

    def test_real_delay_cohort_and_missing_definition_have_different_trajectories(self):
        slip, answer = self.investigate("delivery_slip", "slip")
        missing, clarification = self.investigate("missing_definition", "missing")
        self.assertEqual(answer["status"], "answered")
        group = next(e for e in events(slip) if e["tool"] == "analyze"
                     and e["input"]["operation"] == "cohort_change")["result"]["data"]["groups"][0]
        self.assertEqual(group["group"], "North")
        self.assertEqual(group["non_success_count_change"], 6)
        self.assertEqual(clarification["status"], "needs_clarification")
        self.assertEqual(len(clarification["answer"]["questions"]), 2)
        self.assertFalse(any(e["tool"] == "query" for e in events(missing)))
        self.assertNotEqual([e["tool"] for e in events(slip)], [e["tool"] for e in events(missing)])
        self.assertEqual(verify(slip), 12)
        self.assertEqual(verify(missing), 3)

    def test_opaque_same_path_changed_data_changes_tool_trace(self):
        # The driver cannot see fixture path; same goal, same opaque directory.
        bundle = self.root / "opaque"
        shutil.copytree(FIXTURES / "join_multiplier", bundle)
        run(GOAL, bundle, self.root / "a", ScriptedMock())
        first = events(self.root / "a")
        for source in (FIXTURES / "delivery_slip").iterdir():
            shutil.copyfile(source, bundle / source.name)
        run(GOAL, bundle, self.root / "b", ScriptedMock())
        second = events(self.root / "b")
        self.assertTrue(any("COUNT(DISTINCT" in e["input"].get("sql", "") for e in first))
        self.assertFalse(any("COUNT(DISTINCT" in e["input"].get("sql", "") for e in second))
        self.assertTrue(any(e["input"].get("operation") == "cohort_change" for e in second))

    def test_notebook_cells_reexecute_actual_actions_without_provider(self):
        path, _ = self.investigate("join_multiplier", inject=True)
        # This test executes only our trusted exporter template; provider text is JSON data.
        script = (
            "import json\n"
            "n=json.load(open('investigation.ipynb'))\n"
            "scope={}\n"
            "for c in n['cells']:\n"
            " if c['cell_type']=='code': exec(compile(''.join(c['source']), '<notebook>', 'exec'), scope)\n"
            "print('ALL NOTEBOOK CELLS VERIFIED')\n"
        )
        completed = subprocess.run([sys.executable, "-I", "-c", script], cwd=path,
                                   capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("ALL NOTEBOOK CELLS VERIFIED", completed.stdout)
        self.assertIn("no such column", completed.stdout)

    def test_readonly_and_no_host_file_or_extension_access(self):
        runtime = self.runtime()
        database = runtime.snapshot / "data.sqlite"
        before = digest(database.read_bytes())
        canary = self.root / "canary.txt"
        canary.write_text("PRIVATE-CANARY")
        denied = [
            "DELETE FROM orders", "UPDATE orders SET order_status='cancelled'",
            "DROP TABLE orders", "CREATE TABLE injected(x)", "PRAGMA query_only=OFF",
            "PRAGMA writable_schema=ON", f"ATTACH DATABASE '{self.root / 'escape.db'}' AS x",
            "SELECT load_extension('/tmp/nonexistent')",
            f"SELECT readfile('{canary}')", "SELECT writefile('/tmp/escape','bad')",
            "SELECT 1; DELETE FROM orders", "VACUUM INTO '/tmp/escape.db'",
            "WITH x AS (SELECT 1) DELETE FROM orders",
        ]
        for i, sql in enumerate(denied):
            with self.subTest(sql=sql):
                result = runtime.call(f"d{i}", "query", {"sql": sql})
                self.assertFalse(result["ok"], result)
                self.assertNotIn("PRIVATE-CANARY", json.dumps(result))
        self.assertEqual(digest(database.read_bytes()), before)
        self.assertEqual(canary.read_text(), "PRIVATE-CANARY")
        self.assertFalse((self.root / "escape.db").exists())
        self.assertTrue(runtime.call("good", "query", {"sql": "SELECT COUNT(*) AS n FROM orders"})["ok"])

    def test_sql_work_and_output_limits_are_visible(self):
        runtime = self.runtime()
        start = time.monotonic()
        result = runtime.call("expensive", "query", {"sql": """
WITH RECURSIVE seq(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM seq WHERE x<100000000)
SELECT SUM(x) AS n FROM seq
"""})
        self.assertFalse(result["ok"])
        self.assertLess(time.monotonic() - start, 4)
        big = runtime.call("oversized", "query", {
            "sql": "SELECT group_concat(printf('%1000s','a'), '') AS s FROM orders a, orders b"})
        self.assertFalse(big["ok"])
        rows = runtime.call("rows", "query", {"sql": """
WITH RECURSIVE seq(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM seq WHERE x<300)
SELECT x AS period, 1 AS on_time, 2 AS total FROM seq
"""})
        self.assertTrue(rows["ok"])
        self.assertTrue(rows["data"]["truncated"])
        self.assertEqual(rows["data"]["row_count"], 200)
        stats = runtime.call("stats", "analyze", {
            "operation": "compare_rates", "evidence_id": "rows", "period": "period",
            "baseline": "1", "current": "2", "successes": "on_time", "total": "total"})
        self.assertFalse(stats["ok"])
        self.assertIn("truncated", stats["error"]["message"])

    def test_tool_path_and_arbitrary_python_are_not_capabilities(self):
        runtime = self.runtime()
        for index, (name, args) in enumerate([
            ("read_context", {"document": "/etc/passwd"}),
            ("read_context", {"document": "../catalog"}),
            ("python", {"code": "__import__('os').environ"}),
            ("query", {"sql": "SELECT 1", "database": "/tmp/other.sqlite"}),
        ]):
            self.assertFalse(runtime.call(f"x{index}", name, args)["ok"])

    def test_finish_rejects_fabricated_or_failed_evidence(self):
        runtime = self.runtime()
        args = {"status": "answered", "summary": "Invented", "questions": [],
                "findings": [{"text": "Invented rate", "evidence": ["e999"]}]}
        self.assertFalse(runtime.call("finish", "finish", args)["ok"])
        self.assertIsNone(runtime.finished)
        runtime.call("failed", "query", {"sql": "SELECT missing FROM orders"})
        args["findings"][0]["evidence"] = ["failed"]
        self.assertFalse(runtime.call("finish2", "finish", args)["ok"])

    def test_snapshot_integrity_no_source_mutation_and_no_clobber(self):
        source = FIXTURES / "join_multiplier"
        before = {p.name: digest(p.read_bytes()) for p in source.iterdir()}
        path, _ = self.investigate("join_multiplier")
        self.assertEqual(before, {p.name: digest(p.read_bytes()) for p in source.iterdir()})
        with self.assertRaises(FileExistsError):
            run(GOAL, source, path, ScriptedMock())
        target = path / "input" / "orders.csv"
        target.chmod(0o644)
        target.write_text(target.read_text() + "tamper")
        with self.assertRaisesRegex(ValueError, "Input hash mismatch"):
            Replay(path)

    def test_loader_rejects_symlink_traversal_non_synthetic_and_malformed_csv(self):
        for index, mutation in enumerate(("symlink", "path", "synthetic", "csv")):
            root = self.root / f"fixture-{index}"
            shutil.copytree(FIXTURES / "delivery_slip", root)
            catalog = json.loads((root / "catalog.json").read_text())
            if mutation == "symlink":
                (root / "orders.csv").unlink()
                (root / "orders.csv").symlink_to(FIXTURES / "delivery_slip" / "orders.csv")
            elif mutation == "path":
                catalog["tables"][0]["path"] = "../outside.csv"
            elif mutation == "synthetic":
                catalog["synthetic"] = False
            else:
                (root / "orders.csv").write_text("bad,column\n1\n")
            (root / "catalog.json").write_text(json.dumps(catalog))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                prepare_bundle(root, self.root / f"out-{index}")

    def test_public_csv_contract_null_and_numeric_types(self):
        runtime = self.runtime()
        r = runtime.call("q", "query", {"sql": """
SELECT typeof(ordered_units) AS kind, COUNT(*) AS n
FROM orders WHERE completed_at_utc IS NULL GROUP BY typeof(ordered_units)
"""})
        self.assertEqual(r["data"]["rows"], [{"kind": "integer", "n": 3}])
        schema = runtime.call("s", "inspect_schema", {})
        self.assertEqual(len(schema["data"]["tables"]), 5)

    def test_generic_inspection_cli_without_provider(self):
        output = self.root / "inspection"
        with contextlib.redirect_stdout(io.StringIO()):
            status = main(["inspect", "--fixture", str(FIXTURES / "delivery_slip"),
                           "--out", str(output)])
        self.assertEqual(status, 0)
        self.assertEqual(len(json.loads((output / "schema.json").read_text())["data"]["tables"]), 5)
        self.assertFalse((output / "report.json").exists())

    def test_provider_failure_step_limit_and_deadline_export_failure(self):
        path, result = self.investigate("delivery_slip", max_steps=1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure"]["reason"]["code"], "finalization_tool_required")
        self.assertTrue((path / "report.html").exists())

        class Failing:
            mode = "mock-scripted"
            label = "test stub"

            def next(self, *args):
                raise RuntimeError("secret-credential-canary")

        out = self.root / "provider"
        result = run(GOAL, FIXTURES / "delivery_slip", out, Failing())
        self.assertEqual(result["failure"]["type"], "ProviderFailure")
        self.assertNotIn("secret-credential-canary", (out / "trace.jsonl").read_text())

        class Slow(Failing):
            def next(self, *args):
                time.sleep(3)

        result = run(GOAL, FIXTURES / "delivery_slip", self.root / "timeout", Slow(), max_seconds=1)
        self.assertEqual(result["failure"]["type"], "TimeoutError")
        self.assertEqual(result["status"], "failed")

    def test_provider_exception_canaries_never_reach_public_or_persisted_output(self):
        canaries = [
            "FAKE-SECRET-REDACTION-CANARY",
            "https://request-canary.invalid/private?api_key=FAKE",
            "Authorization: Bearer FAKE-TOKEN",
        ]
        for exception_type in (TimeoutError, ConnectionError, RuntimeError):
            with self.subTest(exception_type=exception_type.__name__):
                class Failing:
                    mode = "mock-scripted"
                    label = "MOCK exception redaction test; no network"

                    def next(self, *args):
                        raise exception_type("\n".join(canaries))

                output = self.root / exception_type.__name__
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with patch("investigator.mock.ScriptedMock", return_value=Failing()):
                        status = main(["run", "--fixture", str(FIXTURES / "delivery_slip"),
                                       "--out", str(output)])
                self.assertEqual(status, 1)
                public = stdout.getvalue() + stderr.getvalue()
                self.assertIn("ERROR", public)
                result = json.loads((output / "report.json").read_text())
                self.assertEqual(result["status"], "failed")
                expected_type = "TimeoutError" if exception_type is TimeoutError else "ProviderFailure"
                self.assertEqual(result["failure"]["type"], expected_type)
                self.assertIn("redacted", result["failure"]["message"])
                for canary in canaries:
                    self.assertNotIn(canary, public)
                    for artifact in output.rglob("*"):
                        if artifact.is_file():
                            self.assertNotIn(canary.encode(), artifact.read_bytes(), str(artifact))

    def assert_same_period_is_recoverable(self, operation):
        runtime = self.runtime()
        source = runtime.call("source", "query", {"sql": """
SELECT 'A' AS period, 'North' AS region, 10 AS total, 9 AS on_time
UNION ALL SELECT 'B', 'North', 10, 5
"""})
        self.assertTrue(source["ok"])
        args = {
            "operation": operation, "evidence_id": "source", "period": "period",
            "baseline": "A", "current": "A", "successes": "on_time", "total": "total",
        }
        if operation == "cohort_change":
            args["group"] = "region"
        rejected = runtime.call("invalid", "analyze", args)
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["type"], "ValueError")
        self.assertIn("distinct periods", rejected["error"]["message"])
        corrected = runtime.call("corrected", "analyze", {**args, "current": "B"})
        self.assertTrue(corrected["ok"])
        data = corrected["data"]
        if operation == "cohort_change":
            data = data["groups"][0]
        self.assertAlmostEqual(data["delta_percentage_points"], -40.0)

    def test_compare_rates_rejects_identical_periods_then_accepts_correction(self):
        self.assert_same_period_is_recoverable("compare_rates")

    def test_cohort_change_rejects_identical_periods_then_accepts_correction(self):
        self.assert_same_period_is_recoverable("cohort_change")

    def test_deepseek_protocol_feedback_adapter_without_network(self):
        requests = []

        def parent_stub(payload, *, timeout_seconds, budget_reference):
            self.assertEqual(budget_reference, "existing-parent-budget-test-only")
            self.assertGreater(timeout_seconds, 0)
            self.assertEqual(payload["max_tokens"], 2048)
            self.assertTrue(payload["tools"])
            requests.append(payload)
            n = len(requests)
            if n == 1:
                action = selection(n, "query", {"sql": "SELECT missing FROM orders"}, "协议桩：错误查询")
            elif n == 2:
                observation = json.loads(payload["messages"][-1]["content"])
                self.assertFalse(observation["ok"])
                self.assertEqual(payload["messages"][-1]["tool_call_id"], "call_1")
                action = selection(n, "inspect_schema", {}, "协议桩：实际反馈后查 schema")
            elif n == 3:
                schema = json.loads(payload["messages"][-1]["content"])["data"]
                self.assertIn("orders", [t["name"] for t in schema["tables"]])
                action = selection(n, "query", {"sql": "SELECT COUNT(*) AS n FROM orders"},
                                   "协议桩：新的有效查询")
            else:
                observation = json.loads(payload["messages"][-1]["content"])
                self.assertEqual(observation["data"]["rows"], [{"n": 42}])
                action = selection(n, "finish", {
                    "status": "answered", "summary": "协议测试计数完成",
                    "findings": [{"text": "42 orders in fixture", "evidence": [observation["evidence_id"]]}],
                    "questions": [],
                }, "协议桩：引用真实返回值")
            action["reasoning_content"] = "PRIVATE-REASONING-CANARY"
            return {"choices": [{"message": action}]}

        provider = DeepSeekProvider(parent_stub, model="parent-selected-model",
                                    parent_budget_reference="existing-parent-budget-test-only")
        provider.mode = "mock-scripted"  # This is a no-network protocol test, never live evidence.
        provider.label = "MOCK DeepSeek protocol test transport"
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            out = self.root / "protocol"
            result = run(GOAL, FIXTURES / "delivery_slip", out, provider)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["live_calls"], 0)
        self.assertEqual(len(requests), 4)
        self.assertNotIn("PRIVATE-REASONING-CANARY", (out / "trace.jsonl").read_text())
        self.assertFalse(any("reasoning_content" in m for m in requests[-1]["messages"]))

    def test_live_cli_stops_without_credentials_or_network(self):
        with contextlib.redirect_stderr(io.StringIO()) as stream:
            with patch("os.getenv", side_effect=AssertionError("credential/env access forbidden")):
                code = main(["run", "--mode", "live", "--fixture", "absent", "--out", "absent"])
        self.assertEqual(code, 2)
        self.assertIn("LIVE_TRANSPORT_REQUIRED", stream.getvalue())

    def test_invalid_provider_message_is_visible(self):
        class Invalid:
            mode = "mock-scripted"
            label = "malformed protocol stub"

            def next(self, *args):
                return {"role": "assistant", "tool_calls": []}

        result = run(GOAL, FIXTURES / "delivery_slip", self.root / "invalid", Invalid())
        self.assertEqual(result["status"], "failed")
        self.assertIn("1..4 tool calls", result["failure"]["message"])


if __name__ == "__main__":
    unittest.main()
