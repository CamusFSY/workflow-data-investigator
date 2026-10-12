import copy
import json
import subprocess
import sys
from pathlib import Path

from .analytics import analyze, bar_chart
from .bundle import CONTEXT_FILES, safe_read
from .provenance import source_provenance
from .evidence import (FinishValidationError, freeze_answer_contract, role_finish_tool,
                       validate_evidence_roles, validate_finish_structure, reject)


def tool(name, description, properties, required):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties,
                       "required": required, "additionalProperties": False},
    }}


STRING = {"type": "string"}
RATE_FIELDS = {k: STRING for k in
               ("evidence_id", "period", "baseline", "current", "successes", "total")}
TOOLS = [
    tool("read_context", "Read public catalog, metric definition, dashboard SQL, or request.",
         {"document": {"type": "string", "enum": list(CONTEXT_FILES)}}, ["document"]),
    tool("inspect_schema", "Inspect actual imported SQLite tables and columns.", {}, []),
    tool("query", "Execute one bounded, read-only SQLite SELECT/WITH. Errors are observations.",
         {"sql": STRING}, ["sql"]),
    tool("analyze", "Compute untyped successes/total ratios from a complete query result. "
         "non_successes means total minus successes, not necessarily late. Column names do not validate metric meaning.",
         {**RATE_FIELDS, "group": STRING,
          "operation": {"type": "string", "enum": ["compare_rates", "cohort_change"]}},
         [*RATE_FIELDS, "operation"]),
    tool("plot", "Draw untyped successes/total ratios with source column labels from a complete query "
         "(at most 12 rows). No on-time or late meaning is inferred.",
         {k: STRING for k in ("evidence_id", "label", "successes", "total")},
         ["evidence_id", "label", "successes", "total"]),
    tool("finish", "Deliver cited findings, explicit conditional findings, or clarification questions. "
         "All questions and assumptions persist across attempts; removing them does not resolve them.",
         {"status": {"type": "string", "enum": ["answered", "conditional", "needs_clarification"]},
          "summary": STRING,
          "findings": {"type": "array", "items": {
              "type": "object", "properties": {
                  "text": STRING,
                  "evidence": {"type": "array", "items": STRING}},
              "required": ["text", "evidence"], "additionalProperties": False}},
          "questions": {"type": "array", "items": STRING},
          "conditions": {"type": "array", "items": STRING}},
         ["status", "summary", "findings", "questions"]),
]

# Trusted caller input, deliberately absent from TOOLS. A model cannot invoke this schema.
RESOLUTIONS = {"type": "array", "items": {
    "type": "object", "properties": {
        "question_id": STRING, "answer": STRING,
        "source_kind": {"type": "string", "enum": ["user", "authority"]},
        "source_reference": STRING},
    "required": ["question_id", "answer", "source_kind", "source_reference"],
    "additionalProperties": False}}


def validate(value, schema):
    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict):
            raise ValueError("Tool arguments must be an object")
        if set(value) - set(schema["properties"]):
            raise ValueError("Unknown argument keys")
        if set(schema.get("required", [])) - set(value):
            raise ValueError("Missing required argument keys")
        for key, item in value.items():
            validate(item, schema["properties"][key])
    elif kind == "string":
        if not isinstance(value, str) or len(value) > 8192:
            raise ValueError("Expected a bounded string")
    elif kind == "array":
        if not isinstance(value, list) or len(value) > 20:
            raise ValueError("Expected an array with at most 20 items")
        for item in value:
            validate(item, schema["items"])
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("Value is outside the allowed enumeration")


class Runtime:
    def __init__(self, snapshot, *, provenance=None, answer_contract=None):
        self.snapshot = Path(snapshot)
        self.provenance = copy.deepcopy(provenance) if provenance is not None else source_provenance(
            json.loads(safe_read(self.snapshot, "catalog.json", 65536)))
        self.results = {}
        self.names = {}
        self.finished = None
        self.clarifications = []
        self.clarification_block = None
        self.answer_contract = freeze_answer_contract(answer_contract)
        self.tools = copy.deepcopy(TOOLS)
        if self.answer_contract is not None:
            self.tools[-1] = role_finish_tool(self.tools[-1])

    def clarification_state(self):
        return copy.deepcopy(self.clarifications)

    def open_questions(self):
        return [item["question"] for item in self.open_blockers() if item["kind"] == "question"]

    def open_conditions(self):
        return [item["question"] for item in self.open_blockers() if item["kind"] == "assumption"]

    def open_blockers(self):
        return [item for item in self.clarification_state() if item["resolution"] is None]

    def remember_blockers(self, questions, conditions, evidence_id):
        if self.clarification_block:
            raise ValueError(self.clarification_block["message"])
        proposed = self.clarification_state()
        has_blank = False
        # Ingest both fields before reporting recoverable blank/summary/evidence errors.
        for kind, values in (("question", questions), ("assumption", conditions)):
            for text in values:
                text = " ".join(text.split())
                if not text:
                    has_blank = True
                    continue
                if not any(item["kind"] == kind and item["question"] == text for item in proposed):
                    proposed.append({"id": f"q{len(proposed) + 1:03d}", "kind": kind,
                                     "question": text, "raised_at": evidence_id, "resolution": None})
        if len(proposed) > 20 or len(json.dumps(proposed, ensure_ascii=False).encode()) > 24000:
            # Keep bounded storage, but never forget that an additional blocker was declared.
            self.clarification_block = {"raised_at": evidence_id, "message":
                "Clarification capacity exceeded (20 questions/assumptions / 24000 bytes); "
                "this run is blocked and cannot finish."}
            raise ValueError(self.clarification_block["message"])
        self.clarifications = proposed
        if has_blank:
            raise ValueError("Questions and conditions must not be blank; all nonblank blockers were retained")

    def apply_clarifications(self, evidence_id, resolutions):
        """Only a trusted host may supply verified user/authority resolutions, never the model."""
        if evidence_id in self.results:
            raise ValueError("Evidence IDs cannot be reused")
        validate(resolutions, RESOLUTIONS)
        if not resolutions or len(json.dumps(resolutions, ensure_ascii=False).encode()) > 12000:
            raise ValueError("External clarifications must be nonempty and <=12000 bytes")
        proposed = self.clarification_state()
        seen = set()
        for resolution in resolutions:
            qid = resolution["question_id"]
            item = next((item for item in proposed if item["id"] == qid), None)
            if item is None or item["resolution"] is not None or qid in seen:
                raise ValueError("External clarification must resolve distinct, open question IDs")
            if not resolution["answer"].strip() or not resolution["source_reference"].strip():
                raise ValueError("External clarification needs an answer and source reference")
            seen.add(qid)
            item["resolution"] = {**copy.deepcopy(resolution), "received_at": evidence_id}
        if len(json.dumps(proposed, ensure_ascii=False).encode()) > 24000:
            raise ValueError("Clarification state exceeds 24000 bytes")
        self.clarifications = proposed
        result = {"ok": True, "data": {"resolutions": copy.deepcopy(resolutions),
                                       "clarifications": self.clarification_state()}}
        self.results[evidence_id] = result
        self.names[evidence_id] = "external_clarification"
        return result

    def sql(self, operation, sql=None):
        payload = json.dumps({"operation": operation, "sql": sql})
        try:
            result = subprocess.run(
                [sys.executable, "-I", str(Path(__file__).with_name("sql_worker.py")),
                 str(self.snapshot / "data.sqlite")],
                input=payload, text=True, capture_output=True, timeout=3,
                cwd=self.snapshot, env={"LANG": "C.UTF-8"}, check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": {
                "type": "QueryLimit", "message": "SQL worker exceeded the 3 second deadline"}}
        if result.returncode != 0:
            return {"ok": False, "error": {
                "type": "QueryLimit", "message": f"SQL worker exited {result.returncode}"}}
        return json.loads(result.stdout)

    def rows(self, evidence_id):
        entry = self.results.get(evidence_id)
        if not entry or not entry["ok"] or self.names[evidence_id] != "query":
            raise ValueError("Analysis requires a successful query evidence_id")
        if entry["data"]["truncated"]:
            raise ValueError("Cannot analyze truncated rows; aggregate in SQL first")
        return entry["data"]["rows"]

    def finish(self, args, evidence_id):
        # Retain declared blockers even when this finish attempt is rejected below.
        self.remember_blockers(args["questions"], args.get("conditions", []), evidence_id)
        conditions = self.open_conditions()
        if not args["summary"].strip() or not args["findings"]:
            if self.answer_contract is not None:
                reject("finish_argument_empty", "summary" if not args["summary"].strip() else "findings",
                       "Provide a nonblank summary and nonempty findings")
            raise ValueError("Provide a summary and cited findings")
        refs = []
        for finding in args["findings"]:
            if self.answer_contract is not None:
                if not finding["text"].strip():
                    reject("finish_finding_empty", "findings", "Each finding needs nonblank text")
                continue
            if not finding["text"].strip() or not finding["evidence"]:
                raise ValueError("Each finding needs text and evidence")
            for ref in finding["evidence"]:
                if ref not in self.results or not self.results[ref]["ok"]:
                    raise ValueError(f"Unknown or unsuccessful evidence reference: {ref}")
                refs.append(ref)
        if self.answer_contract is not None:
            refs = validate_evidence_roles(args, self.results, self.names, self.answer_contract)
        pending = self.open_questions()
        if args["status"] == "needs_clarification" and not self.open_blockers():
            raise ValueError("Clarification must ask specific questions")
        if args["status"] == "conditional" and not conditions:
            raise ValueError("Conditional output must state explicit conditions and cite measured evidence")
        if args["status"] == "answered" and (pending or conditions):
            raise ValueError("Unresolved questions or assumptions prevent answered. Use needs_clarification "
                             "or conditional with explicit conditions. Deleting questions or adding SQL "
                             "does not resolve them; verified external clarification is required.")
        if args["status"] in {"answered", "conditional"}:
            if not any(self.names[ref] in {"query", "analyze"} for ref in refs):
                raise ValueError("An answer must cite measured query or analysis evidence")
        self.finished = {**copy.deepcopy(args), "questions": pending, "conditions": conditions,
                         "clarifications": self.clarification_state()}
        return self.finished

    def call(self, evidence_id, name, args):
        try:
            if evidence_id in self.results:
                raise ValueError("Evidence IDs cannot be reused")
            schema = next((t["function"]["parameters"] for t in self.tools
                           if t["function"]["name"] == name), None)
            if schema is None:
                raise ValueError(f"Unknown tool: {name}")
            if name == "finish" and self.answer_contract is not None:
                validate_finish_structure(args, schema)
            else:
                validate(args, schema)
            if len(json.dumps(args, ensure_ascii=False).encode()) > 12000:
                raise ValueError("Tool arguments exceed 12 KiB")
            if name == "read_context":
                document = args["document"]
                raw = safe_read(self.snapshot, CONTEXT_FILES[document], 65536).decode("utf-8")
                data = json.loads(raw) if document == "catalog" else {"text": raw}
            elif name == "inspect_schema":
                result = self.sql("schema")
            elif name == "query":
                result = self.sql("query", args["sql"])
            elif name == "analyze":
                data = {**analyze(self.rows(args["evidence_id"]), args),
                        "source_evidence_id": args["evidence_id"]}
            elif name == "plot":
                data = {**bar_chart(self.rows(args["evidence_id"]), args, provenance=self.provenance),
                        "source_evidence_id": args["evidence_id"]}
            else:
                data = self.finish(args, evidence_id)
            if name not in {"query", "inspect_schema"}:
                result = {"ok": True, "data": data}
        except Exception as exc:
            result = {"ok": False, "error": {
                "type": type(exc).__name__, "message": str(exc)[:500]}}
            if isinstance(exc, FinishValidationError):
                result["error"].update(code=exc.code, field=exc.field)
            if name == "finish" and self.clarifications:
                result["clarifications"] = self.clarification_state()
            if name == "finish" and self.clarification_block:
                result["clarification_block"] = copy.deepcopy(self.clarification_block)
        self.results[evidence_id] = result
        self.names[evidence_id] = name
        return result
