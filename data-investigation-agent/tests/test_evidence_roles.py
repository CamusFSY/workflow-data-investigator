"""Fresh tiny offline data. No measured BIRD tasks, gold in contracts, or API calls."""
from contextlib import redirect_stdout
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from investigator.bundle import prepare_bundle
from investigator.evidence import freeze_answer_contract, contract_digest
from investigator.loop import run, SYSTEM
from investigator.providers import selection
from investigator.recording import RecordedProvider
from investigator.replay import Replay, verify
from investigator.runtime import Runtime, TOOLS


COUNT_CONTRACT = {"columns": [{"name": "order_count", "type": "integer"}], "min_rows": 1, "max_rows": 1}
RANK_CONTRACT = {"columns": [{"name": "category", "type": "string", "nullable": True},
                              {"name": "item_count", "type": "integer"},
                              {"name": "position", "type": "integer"}], "min_rows": 1, "max_rows": 200}
COUNT_SQL = "SELECT COUNT(DISTINCT o.id) AS order_count FROM orders o JOIN scans s ON s.order_id=o.id WHERE o.region='North'"
RANK_SQL = "SELECT category, COUNT(*) AS item_count, RANK() OVER (ORDER BY COUNT(*) DESC) AS position FROM inventory GROUP BY category ORDER BY item_count DESC"


def fresh_bundle(root):
    source = root / "fresh-source"
    source.mkdir()
    catalog = {"synthetic": True, "csv_null_encoding": "backslash-N", "tables": [
        {"name": "orders", "file": "orders.csv", "columns": {"id": "INTEGER", "region": "TEXT"}},
        {"name": "scans", "file": "scans.csv", "columns": {"id": "INTEGER", "order_id": "INTEGER"}},
        {"name": "inventory", "file": "inventory.csv", "columns": {"id": "INTEGER", "category": "TEXT"}},
    ]}
    (source / "catalog.json").write_text(json.dumps(catalog))
    (source / "orders.csv").write_text("id,region\n11,North\n12,North\n13,South\n")
    (source / "scans.csv").write_text("id,order_id\n1,11\n2,11\n3,12\n4,13\n")
    (source / "inventory.csv").write_text("id,category\n1,Widgets\n2,Widgets\n3,Widgets\n4,Widgets\n5,Cables\n6,Cables\n7,\\N\n8,\\N\n9,Unknown\n")
    for name, text in {"metric_definition.md": "Count distinct North orders with scans. Inventory ranks count rows and retain a NULL category.",
                       "dashboard_query.sql": "-- No dashboard SQL", "request.txt": "Fresh offline task; no expected numerical result provided."}.items():
        (source / name).write_text(text + "\n")
    return source


def finish(answer="count-result", supports=(), status="answered"):
    args = {"status": status, "summary": "Offline fixture result", "findings": [{"text": "Measured answer with separately identified support."}],
            "supporting_evidence_ids": list(supports), "questions": []}
    if answer is not None:
        args["answer_evidence_id"] = answer
    return args


def independent_count_evaluation(source, answer, results):
    """Test-only oracle: calculate from fresh CSV rows, outside the runtime and prompts."""
    with (source / "orders.csv").open() as stream:
        north = {row["id"] for row in csv.DictReader(stream) if row["region"] == "North"}
    with (source / "scans.csv").open() as stream:
        scanned = {row["order_id"] for row in csv.DictReader(stream)}
    expected = [{"order_count": len(north & scanned)}]
    selected_id = answer["answer_evidence_id"]
    observed = results[selected_id]["data"]["rows"]
    return {"answer_evidence_id": selected_id, "expected_rows": expected,
            "observed_rows": observed, "numerically_correct": observed == expected}


class EvidenceRoles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="evidence-roles-offline-")
        self.root = Path(self.tmp.name)
        self.source = fresh_bundle(self.root)
        self.prepared = self.root / "snapshot"
        prepare_bundle(self.source, self.prepared)
        self.runtime = Runtime(self.prepared / "input", answer_contract=COUNT_CONTRACT)

    def tearDown(self):
        self.tmp.cleanup()

    def query(self, sql=COUNT_SQL, ref="count-result", runtime=None):
        result = (runtime or self.runtime).call(ref, "query", {"sql": sql})
        self.assertTrue(result["ok"], result)
        return result

    def rejected(self, args, code, field="answer_evidence_id", runtime=None):
        runtime = runtime or self.runtime
        result = runtime.call("finish-" + str(len(runtime.results)), "finish", args)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["error"]["code"], code)
        self.assertEqual(result["error"]["field"], field)
        self.assertIsNone(runtime.finished)
        return result

    def test_valid_answer_with_multiple_supports(self):
        self.query()
        self.query("SELECT COUNT(*) AS joined_rows,COUNT(DISTINCT o.id) AS unique_orders FROM orders o JOIN scans s ON o.id=s.order_id WHERE o.region='North'", "grain-check")
        self.runtime.call("schema-check", "inspect_schema", {})
        self.runtime.call("metric-context", "read_context", {"document": "metric"})
        result = self.runtime.call("finished", "finish", finish(supports=["grain-check", "schema-check", "metric-context"]))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["answer_evidence_id"], "count-result")
        self.assertEqual(result["data"]["supporting_evidence_ids"], ["grain-check", "schema-check", "metric-context"])
        self.assertNotIn("evidence", result["data"]["findings"][0])

    def test_valid_answer_with_no_support(self):
        self.query()
        self.assertTrue(self.runtime.call("done", "finish", finish())["ok"])

    def test_missing_answer_never_inferred_from_candidates(self):
        self.query(); self.query("SELECT 123 AS order_count", "other-candidate")
        self.rejected(finish(None, ["count-result", "other-candidate"]), "answer_reference_required")

    def test_multiple_answer_ids_are_rejected(self):
        self.query(); self.query("SELECT 123 AS order_count", "other-candidate")
        self.rejected(finish(["count-result", "other-candidate"]), "answer_reference_ambiguous")

    def test_unknown_and_other_run_answers_are_rejected(self):
        other = Runtime(self.prepared / "input", answer_contract=COUNT_CONTRACT)
        self.query(ref="only-in-other-run", runtime=other)
        for ref in ("unknown", "only-in-other-run", ""):
            with self.subTest(ref=ref):
                self.rejected(finish(ref), "answer_reference_required" if not ref else "answer_source_invalid")

    def test_failed_answer_is_rejected(self):
        self.assertFalse(self.runtime.call("bad", "query", {"sql": "SELECT missing FROM orders"})["ok"])
        self.rejected(finish("bad"), "answer_source_invalid")

    def test_truncated_answer_is_rejected(self):
        sql = "WITH RECURSIVE nums(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM nums WHERE n<201) SELECT n AS order_count FROM nums"
        result = self.query(sql, "too-many")
        self.assertTrue(result["data"]["truncated"])
        self.rejected(finish("too-many"), "answer_truncated")

    def test_context_or_schema_cannot_be_the_answer(self):
        self.runtime.call("context", "read_context", {"document": "metric"})
        self.runtime.call("schema", "inspect_schema", {})
        for ref in ("context", "schema"):
            self.rejected(finish(ref), "answer_source_type")

    def test_wrong_columns_and_extra_columns_rejected(self):
        for i, sql in enumerate(("SELECT COUNT(*) AS wrong_name FROM orders", "SELECT 2 AS order_count,3 AS extra")):
            ref=f"wrong-cols-{i}"; self.query(sql, ref)
            self.rejected(finish(ref), "answer_columns_mismatch", "answer_evidence_id.columns")

    def test_wrong_types_and_null_rejected(self):
        for i, sql in enumerate(("SELECT '2' AS order_count", "SELECT 2.5 AS order_count", "SELECT NULL AS order_count")):
            ref=f"wrong-type-{i}";self.query(sql,ref)
            self.rejected(finish(ref), "answer_value_type", "answer_evidence_id.rows[0].order_count")

    def test_boolean_is_not_an_integer_count(self):
        # SQLite emits integer booleans. This host-result fixture covers JSON bool explicitly.
        self.runtime.results["boolean"]={"ok":True,"data":{"columns":["order_count"],"rows":[{"order_count":True}],"row_count":1,"truncated":False}}
        self.runtime.names["boolean"]="query"
        self.rejected(finish("boolean"), "answer_value_type", "answer_evidence_id.rows[0].order_count")

    def test_wrong_row_count_and_corrupt_row_count_rejected(self):
        for ref,sql in (("empty","SELECT id AS order_count FROM orders WHERE 0"), ("many","SELECT id AS order_count FROM orders")):
            self.query(sql,ref)
            self.rejected(finish(ref), "answer_row_shape_mismatch", "answer_evidence_id.rows")
        self.query()
        self.runtime.results["count-result"]["data"]["row_count"]=2
        self.rejected(finish(), "evidence_row_count_invalid")

    def test_wrong_row_keys_and_column_order_rejected(self):
        self.query()
        self.runtime.results["count-result"]["data"]["rows"][0] = {"other": 2}
        self.rejected(finish(), "answer_row_shape_mismatch", "answer_evidence_id.rows[0]")
        runtime = Runtime(self.prepared / "input", answer_contract=RANK_CONTRACT)
        self.query(RANK_SQL, "ranking", runtime)
        runtime.results["ranking"]["data"]["columns"].reverse()
        self.rejected(finish("ranking"), "answer_columns_mismatch", "answer_evidence_id.columns", runtime)

    def test_shape_correct_wrong_number_accepted_but_independent_evaluator_rejects(self):
        self.query()  # Earlier correct answer must not rescue the selected wrong one.
        self.query("SELECT 999 AS order_count", "selected-wrong")
        accepted=self.runtime.call("done", "finish", finish("selected-wrong", ["count-result"]))
        self.assertTrue(accepted["ok"])
        evaluation = independent_count_evaluation(self.source, accepted["data"], self.runtime.results)
        self.assertFalse(evaluation["numerically_correct"])
        self.assertEqual(evaluation["expected_rows"], [{"order_count": 2}])
        self.assertEqual(evaluation["observed_rows"], [{"order_count": 999}])
        self.assertEqual(accepted["data"]["answer_evidence_id"],"selected-wrong")

    def test_duplicate_support_and_answer_as_support_rejected(self):
        self.query();self.runtime.call("schema", "inspect_schema", {})
        self.rejected(finish(supports=["schema","schema"]),"support_reference_duplicate","supporting_evidence_ids[1]")
        self.rejected(finish(supports=["count-result"]),"support_reference_duplicate","supporting_evidence_ids[0]")

    def test_unknown_failed_truncated_support_rejected_separately(self):
        self.query()
        self.runtime.call("bad", "query", {"sql":"SELECT absent FROM orders"})
        for ref in ("missing","bad"):
            self.rejected(finish(supports=[ref]),"support_source_invalid","supporting_evidence_ids[0]")
        self.query("WITH RECURSIVE t(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM t WHERE n<201) SELECT n FROM t", "long-support")
        self.rejected(finish(supports=["long-support"]),"support_truncated","supporting_evidence_ids[0]")

    def test_model_authored_contract_and_legacy_role_array_rejected(self):
        self.query()
        args=finish();args['answer_contract']=COUNT_CONTRACT
        self.rejected(args,"finish_argument_unknown","answer_contract")
        args=finish();args['findings'][0]['evidence']=['count-result']
        self.rejected(args,"finish_argument_unknown","findings[0].evidence")

    def test_caller_contract_is_copied_and_cannot_contain_gold(self):
        original=copy.deepcopy(COUNT_CONTRACT)
        runtime=Runtime(self.prepared/'input',answer_contract=original)
        original['columns'][0]['name']='changed';original['max_rows']=200
        self.query(runtime=runtime)
        self.assertTrue(runtime.call('done','finish',finish())['ok'])
        with self.assertRaises(ValueError):freeze_answer_contract({**COUNT_CONTRACT,'expected_value':2})
        with self.assertRaises(ValueError):freeze_answer_contract({**COUNT_CONTRACT,'min_rows':True})

    def test_fresh_ranking_preserves_null_and_source_provenance(self):
        runtime=Runtime(self.prepared/'input',answer_contract=RANK_CONTRACT)
        result=self.query(RANK_SQL,'ranking',runtime)
        self.assertEqual(result['data']['row_count'],4)
        rows=result['data']['rows']
        self.assertEqual(sorted(r['position'] for r in rows),[1,2,2,4])
        self.assertEqual({r['category'] for r in rows},{'Widgets','Cables',None,'Unknown'})
        self.assertTrue(runtime.call('done','finish',finish('ranking'))['ok'])
        self.assertEqual(runtime.provenance['type'],'synthetic')

    def test_legacy_multi_reference_call_unchanged_without_opt_in(self):
        runtime=Runtime(self.prepared/'input')
        self.query(runtime=runtime);runtime.call('schema','inspect_schema',{})
        args={'status':'answered','summary':'Legacy','findings':[{'text':'Legacy citations','evidence':['count-result','schema']}],'questions':[]}
        self.assertTrue(runtime.call('done','finish',args)['ok'])
        self.assertEqual(runtime.tools,TOOLS)
        self.assertIsNone(runtime.answer_contract)

    def test_context_metadata_cannot_enable_contract_mode(self):
        catalog_path = self.source / "catalog.json"
        catalog = json.loads(catalog_path.read_text())
        catalog["answer_contract"] = COUNT_CONTRACT
        catalog_path.write_text(json.dumps(catalog))
        snapshot = self.root / "metadata-snapshot"
        prepare_bundle(self.source, snapshot)
        runtime = Runtime(snapshot / "input")
        self.assertIsNone(runtime.answer_contract)
        self.assertEqual(runtime.tools, TOOLS)

    def test_clarification_can_have_only_supporting_context(self):
        self.runtime.call("metric-context", "read_context", {"document": "metric"})
        args = finish(None, ["metric-context"], status="needs_clarification")
        args["questions"] = ["Which period is authorized?"]
        result = self.runtime.call("done", "finish", args)
        self.assertTrue(result["ok"], result)
        self.assertNotIn("answer_evidence_id", result["data"])

    def test_rejected_role_does_not_forget_declared_blocker(self):
        self.query()
        args=finish(None);args['questions']=['Which period is authorized?']
        self.rejected(args,'answer_reference_required')
        second=self.runtime.call('again','finish',finish())
        self.assertFalse(second['ok'])
        self.assertIn('Unresolved questions',second['error']['message'])


def envelope(message):
    return {'model':'offline-recording','usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0},
            'choices':[{'finish_reason':'tool_calls','message':message}]}


class LoopEvidenceRoles(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='role-loop-offline-')
        self.root=Path(self.tmp.name);self.source=fresh_bundle(self.root)

    def tearDown(self):self.tmp.cleanup()

    def provider(self,actions):
        path=self.root/'recording.json'
        path.write_text(json.dumps({'format_version':1,'origin':'hand-authored','responses':[envelope(m) for m in actions]}))
        return RecordedProvider(path)

    def act(self,index,name,args):return selection(index,name,args,'Offline fresh-task fixture')

    def events(self,out):return [json.loads(l) for l in (out/'trace.jsonl').read_text().splitlines()]

    def replay(self,out):
        with redirect_stdout(io.StringIO()):return verify(out)

    def test_normal_turn_feedback_correction_exports_and_replay(self):
        first=self.act(1,'query',{'sql':COUNT_SQL})
        first['tool_calls']+=self.act(2,'inspect_schema',{})['tool_calls']
        first['tool_calls']+=self.act(3,'query',{'sql':'SELECT COUNT(*) AS scans FROM scans'})['tool_calls']
        provider=self.provider([first,self.act(4,'finish',finish(None,['e002','e003'])),self.act(5,'finish',finish('e001',['e002','e003']))])
        recorded_next = provider.next
        requests = []
        def observe(messages, tools, timeout_seconds):
            requests.append(copy.deepcopy({"messages": messages, "tools": tools}))
            return recorded_next(messages, tools, timeout_seconds)
        provider.next = observe
        out=self.root/'corrected'
        result=run('Count North orders with scans.',self.source,out,provider,max_steps=3,max_tool_actions=12,max_seconds=120,answer_contract=COUNT_CONTRACT)
        self.assertEqual(result['status'],'answered')
        self.assertEqual((result['provider_requests'],result['tool_actions'],result['live_calls']),(3,5,0))
        events=self.events(out)
        self.assertEqual(events[3]['result']['error']['field'],'answer_evidence_id')
        self.assertFalse(events[3]['decision_budget']['finish_only'])
        self.assertEqual(events[4]['decision_budget']['remaining_model_turns'],1)
        self.assertEqual(events[4]['decision_budget']['remaining_tool_actions'],8)
        self.assertEqual(result['answer']['answer_evidence_id'],'e001')
        self.assertEqual(result['answer']['supporting_evidence_ids'],['e002','e003'])
        feedback = json.loads(requests[2]['messages'][-1]['content'])
        self.assertEqual(feedback['error']['field'], 'answer_evidence_id')
        self.assertEqual(feedback['error']['code'], 'answer_reference_required')
        self.assertEqual([t['function']['name'] for t in requests[2]['tools']], ['finish'])
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(verify(out), 5)
        self.assertIn('"answer_evidence_id": "e001"', printed.getvalue())
        self.assertIn('"supporting_evidence_ids": ["e002", "e003"]', printed.getvalue())
        self.assertIn('frozen provenance', printed.getvalue())
        self.assertIn('Cite exact evidence IDs in each final finding.', SYSTEM)
        for name in ('report.json','report.html','investigation.ipynb'):
            text=(out/name).read_text()
            self.assertIn('answer_evidence_id',text);self.assertIn('supporting_evidence_ids',text)
        manifest=json.loads((out/'manifest.json').read_bytes())
        self.assertIn('answer_contract.json',manifest['artifacts'])
        self.assertEqual(result['answer_contract_sha256'],contract_digest(freeze_answer_contract(COUNT_CONTRACT)))
        self.assertTrue(all(e['data_provenance']['type']=='synthetic' for e in events))

    def test_final_turn_rejection_never_uses_extra_recording(self):
        provider=self.provider([self.act(1,'query',{'sql':COUNT_SQL}),self.act(2,'finish',finish(None)),self.act(3,'finish',finish('e001'))])
        out=self.root/'last-turn'
        result=run('Count orders.',self.source,out,provider,max_steps=2,max_tool_actions=12,answer_contract=COUNT_CONTRACT)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['failure']['phase'],'finalization_window')
        self.assertEqual((result['provider_requests'],result['tool_actions']),(2,2))
        self.assertIsNone(result['answer'])
        self.assertEqual(self.replay(out),2)

    def test_action_finalization_window_rejection_no_extra_call(self):
        provider=self.provider([self.act(1,'query',{'sql':COUNT_SQL}),self.act(2,'finish',finish(['e001','e002'])),self.act(3,'finish',finish('e001'))])
        out=self.root/'last-actions'
        result=run('Count orders.',self.source,out,provider,max_steps=8,max_tool_actions=5,answer_contract=COUNT_CONTRACT)
        self.assertEqual(result['status'],'failed')
        self.assertEqual((result['provider_requests'],result['tool_actions']),(2,2))
        self.assertEqual(self.events(out)[1]['result']['error']['code'],'answer_reference_ambiguous')

    def test_contract_file_tamper_and_mode_stripping_rejected_on_replay(self):
        provider=self.provider([self.act(1,'query',{'sql':COUNT_SQL}),self.act(2,'finish',finish('e001'))])
        out=self.root/'pinned'
        run('Count orders.',self.source,out,provider,max_steps=2,max_tool_actions=10,answer_contract=COUNT_CONTRACT)
        raw=(out/'answer_contract.json').read_bytes()
        (out/'answer_contract.json').write_bytes(raw+b' ')
        with self.assertRaisesRegex(ValueError,'Artifact hash mismatch'):Replay(out)
        (out/'answer_contract.json').write_bytes(raw)
        manifest=json.loads((out/'manifest.json').read_bytes());manifest.pop('answer_contract')
        (out/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'silently become legacy'):Replay(out)

    def test_model_authored_contract_gets_field_feedback_without_changing_host_contract(self):
        injected=finish('e001');injected['answer_contract']={**COUNT_CONTRACT,'max_rows':200}
        provider=self.provider([self.act(1,'query',{'sql':COUNT_SQL}),self.act(2,'finish',injected),self.act(3,'finish',finish('e001'))])
        out=self.root/'injection'
        result=run('Count orders.',self.source,out,provider,max_steps=3,max_tool_actions=10,answer_contract=COUNT_CONTRACT)
        self.assertEqual(result['status'],'answered')
        self.assertEqual(self.events(out)[1]['result']['error']['field'],'answer_contract')
        self.assertEqual(result['answer_contract']['max_rows'],1)

    def test_invalid_caller_contract_rejected_before_provider_or_artifacts(self):
        provider=self.provider([self.act(1,'inspect_schema',{})])
        out=self.root/'not-created'
        with self.assertRaises(ValueError):run('Task',self.source,out,provider,answer_contract={**COUNT_CONTRACT,'expected_value':2})
        self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
