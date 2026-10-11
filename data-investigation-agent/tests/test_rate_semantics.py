"""SCRIPTED local fixtures: arithmetic must not manufacture business labels."""
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from investigator.bundle import digest, prepare_bundle
from investigator.loop import run
from investigator.providers import selection
from investigator.replay import verify
from investigator.runtime import Runtime

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "rate_meaning"
DISTINCT = "SELECT period, completed, timely, cancelled, total FROM rate_samples WHERE cohort='distinct' ORDER BY period"


def rate_args(source, numerator="completed", denominator="total", **extra):
    return {"operation": "compare_rates", "evidence_id": source,
            "period": "period", "baseline": "baseline", "current": "current",
            "successes": numerator, "total": denominator, **extra}


class ScriptedRates:
    mode = "mock-scripted"
    label = "SCRIPTED rate-meaning regression; no model invocation"

    def __init__(self):
        self.index = 0
        self.responses = [
            selection(1, "query", {"sql": DISTINCT}, "SCRIPTED synthetic count query"),
            selection(2, "analyze", rate_args("e001"), "SCRIPTED completion ratio"),
            selection(3, "plot", {"evidence_id": "e001", "label": "period", "successes": "completed", "total": "total"}, "SCRIPTED plot"),
            selection(4, "analyze", rate_args("e001", "timely"), "SCRIPTED separate numerator"),
            selection(5, "plot", {"evidence_id": "e001", "label": "period", "successes": "timely", "total": "total"}, "SCRIPTED plot"),
            selection(6, "finish", {
                "status": "conditional",
                "summary": "SCRIPTED selected-column ratios under an unapproved interpretation.",
                "findings": [{"text": "completed/total is 8/10 to 5/10; timely/total is 6/10 to 3/10. No causal claim.",
                              "evidence": ["e001", "e002", "e004"]}],
                "conditions": ["Assume the fixture total column is the intended eligible count."],
                "questions": ["Which numerator and eligibility rule are approved?"],
            }, "SCRIPTED qualified interpretation, not an autonomous finding"),
        ]

    def next(self, messages, tools, timeout):
        response = copy.deepcopy(self.responses[self.index])
        self.index += 1
        return response


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.alts = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.alts.append(dict(attrs)["alt"])


class RateSemanticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        prepare_bundle(FIXTURE, self.root / "input-copy")
        self.runtime = Runtime(self.root / "input-copy" / "input")
        self.database_hash = digest((self.runtime.snapshot / "data.sqlite").read_bytes())
        network = patch("socket.socket", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def tearDown(self):
        self.assertEqual(digest((self.runtime.snapshot / "data.sqlite").read_bytes()), self.database_hash)

    def query(self, evidence_id="source", sql=DISTINCT):
        result = self.runtime.call(evidence_id, "query", {"sql": sql})
        self.assertTrue(result["ok"], result)
        return result["data"]

    def analyze(self, evidence_id, args):
        result = self.runtime.call(evidence_id, "analyze", args)
        self.assertTrue(result["ok"], result)
        return result["data"]

    def assert_neutral(self, comparison):
        for period in ("baseline", "current"):
            self.assertNotIn("on_time", comparison[period])
            self.assertNotIn("late", comparison[period])
            self.assertIn("successes", comparison[period])
            self.assertIn("non_successes", comparison[period])
        self.assertNotIn("late_count_change", comparison)
        self.assertIn("non_success_count_change", comparison)

    def test_completion_and_timely_counts_keep_distinct_source_bindings(self):
        self.query()
        complete = self.analyze("completion", rate_args("source"))
        timely = self.analyze("timely", rate_args("source", "timely"))
        self.assertEqual([complete[p]["rate"] for p in ("baseline", "current")], [0.8, 0.5])
        self.assertEqual([timely[p]["rate"] for p in ("baseline", "current")], [0.6, 0.3])
        for item, column in ((complete, "completed"), (timely, "timely")):
            self.assert_neutral(item)
            self.assertEqual(item["rate_semantics"], "untyped_ratio")
            self.assertEqual(item["source_evidence_id"], "source")
            self.assertEqual(item["source_columns"], {"successes": column, "total": "total", "period": "period"})

    def test_cancellations_in_the_complement_are_not_called_late(self):
        rows = self.query()["rows"]
        result = self.analyze("comparison", rate_args("source"))
        self.assert_neutral(result)
        self.assertEqual([result[p]["non_successes"] for p in ("baseline", "current")], [2, 5])
        self.assertEqual(result["non_success_count_change"], 3)
        self.assertEqual([row["cancelled"] for row in rows], [1, 2])
        self.assertEqual([row["total"] - row["completed"] - row["cancelled"] for row in rows], [1, 3])

    def test_equal_ratios_and_equal_aliases_do_not_merge_query_provenance(self):
        results = []
        for source, numerator, denominator in (("complete", "completed", "total"), ("timely", "timely", "completed")):
            sql = f"SELECT period, {numerator} AS value, {denominator} AS n FROM rate_samples WHERE cohort='equal_ratio' ORDER BY period"
            self.query(source, sql)
            results.append(self.analyze(source + "-rate", rate_args(source, "value", "n")))
        self.assertEqual([[r[p]["rate"] for p in ("baseline", "current")] for r in results], [[0.5, 0.75], [0.5, 0.75]])
        self.assertEqual([r["baseline"]["successes"] for r in results], [8, 4])
        self.assertEqual([r["baseline"]["total"] for r in results], [16, 8])
        self.assertEqual(results[0]["source_columns"], results[1]["source_columns"])
        self.assertEqual([r["source_evidence_id"] for r in results], ["complete", "timely"])
        self.assertTrue(all(r["rate_semantics"] == "untyped_ratio" for r in results))

    def test_on_time_alias_cannot_promote_an_untyped_metric(self):
        self.query(sql="SELECT period, completed AS on_time, total FROM rate_samples WHERE cohort='distinct' ORDER BY period")
        args = rate_args("source", "on_time")
        result = self.analyze("analysis", args)
        self.assert_neutral(result)
        self.assertEqual(result["rate_semantics"], "untyped_ratio")
        self.assertEqual(result["source_columns"]["successes"], "on_time")
        rejected = self.runtime.call("fake-contract", "analyze", {**args, "metric_contract": "approved-on-time"})
        self.assertFalse(rejected["ok"])
        self.assertIn("Unknown argument keys", rejected["error"]["message"])

    def test_cohort_change_uses_the_same_neutral_count_contract(self):
        self.query(sql="SELECT * FROM rate_samples ORDER BY cohort, period")
        result = self.analyze("cohorts", rate_args("source", operation="cohort_change", group="cohort"))
        self.assertEqual(result["source_columns"]["group"], "cohort")
        self.assertEqual(result["source_evidence_id"], "source")
        self.assertEqual(result["rate_semantics"], "untyped_ratio")
        self.assertEqual([g["group"] for g in result["groups"]], ["distinct", "equal_ratio"])
        for group in result["groups"]:
            self.assert_neutral(group)

    def test_plot_counts_title_and_escaped_column_provenance_stay_neutral(self):
        column = "completed<&>"
        self.query(sql=f'SELECT period, completed AS "{column}", total FROM rate_samples WHERE cohort=\'distinct\' ORDER BY period')
        result = self.runtime.call("chart", "plot", {"evidence_id": "source", "label": "period", "successes": column, "total": "total"})
        self.assertTrue(result["ok"], result)
        data = result["data"]
        self.assertEqual(data["source_evidence_id"], "source")
        self.assertEqual(data["source_columns"], {"successes": column, "total": "total", "label": "period"})
        self.assertEqual(data["rate_semantics"], "untyped_ratio")
        self.assertEqual(data["points"][0], {"label": "baseline", "rate": 0.8, "successes": 8, "non_successes": 2, "total": 10})
        svg = ET.fromstring(data["svg"])
        self.assertIn("untyped ratios", svg.attrib["aria-label"])
        text = "".join(svg.itertext())
        self.assertIn("Observed ratio · UNTYPED", text)
        self.assertIn(column, text)
        self.assertNotIn("Observed on-time", text)
        self.assertEqual(svg.findall(".//{http://www.w3.org/2000/svg}script"), [])

    def test_report_notebook_and_frozen_replay_preserve_neutral_results(self):
        output = self.root / "scripted-artifacts"
        outcome = run("Compare synthetic selected-column ratios", FIXTURE, output, ScriptedRates(),
                      max_steps=6, max_tool_actions=12)
        self.assertEqual(outcome["status"], "conditional")
        self.assertFalse(outcome["investigation_complete"])
        self.assertEqual(outcome["live_calls"], 0)
        self.assertEqual(outcome["answer"]["questions"], ["Which numerator and eligibility rule are approved?"])
        self.assertEqual(json.loads((output / "report.json").read_text()), outcome)
        events = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
        for event in events:
            if event["tool"] == "analyze":
                self.assert_neutral(event["result"]["data"])
                self.assertEqual(event["result"]["data"]["source_evidence_id"], "e001")
        report = (output / "report.html").read_text()
        parser = Images()
        parser.feed(report)
        self.assertEqual(parser.alts, ["合成数据查询列比率；业务口径未验证"] * 2)
        self.assertIn("successes: completed / total: total", report)
        self.assertIn("successes: timely / total: total", report)
        self.assertIn('源查询 <a href="#e001">e001</a>', report)
        self.assertIn("自由文本解读、因果说法和业务批准仍未经算术验证", report)
        self.assertLess(report.index("业务批准仍未经算术验证"), report.index(outcome["answer"]["summary"]))
        book = json.loads((output / "investigation.ipynb").read_text())
        first = "".join(book["cells"][0]["source"])
        self.assertIn("non_successes 是 total - successes", first)
        self.assertIn("SCRIPTED", first)
        embedded = []
        for cell in book["cells"]:
            if cell["cell_type"] == "code" and "event = " in "".join(cell["source"]):
                # Evaluate only the trusted template's literal JSON argument, not provider code.
                import ast
                tree = ast.parse("".join(cell["source"]))
                embedded.append(json.loads(ast.literal_eval(tree.body[0].value.args[0])))
        self.assertEqual(embedded, events)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify(output), 6)
        completed = subprocess.run([sys.executable, "-I", str(output / "replay.py")], cwd="/tmp",
                                   capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("6 tool results", completed.stdout)
        executed = subprocess.run([sys.executable, "-I", "-c",
            "import json\nbook=json.load(open('investigation.ipynb'))\n"
            "for cell in book['cells']:\n"
            " if cell['cell_type']=='code': exec(compile(''.join(cell['source']), '<trusted-template>', 'exec'))\n"],
            cwd=output, capture_output=True, text=True, timeout=20)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn('"rate_semantics": "untyped_ratio"', executed.stdout)
        self.assertIn('"non_successes": 2', executed.stdout)
        self.assertNotIn('"on_time":', executed.stdout)
        self.assertNotIn('"late":', executed.stdout)


if __name__ == "__main__":
    unittest.main()
