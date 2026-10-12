"""Opt-in, caller-owned answer shape and explicit evidence roles. No gold values."""
import copy
import hashlib
import json
import math
from pathlib import Path

from .bundle import safe_read
from .sql_worker import MAX_QUERY_COLUMNS


def load_answer_contract(path):
    """Read an explicitly selected local contract, never discover one in a bundle."""
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in [path, *path.parents]):
        raise ValueError("Symlink answer contract paths are not accepted")
    value = json.loads(safe_read(path.parent, path.name, 24000))
    if value is None:
        raise ValueError("An answer contract file must contain an object, not null")
    return freeze_answer_contract(value)


class FinishValidationError(ValueError):
    def __init__(self, code, field, message):
        super().__init__(message)
        self.code, self.field = code, field or "$"


def reject(code, field, message):
    raise FinishValidationError(code, field, message)


def freeze_answer_contract(value):
    """Copy only bounded public shape metadata supplied by the trusted Python caller."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"version", "columns", "min_rows", "max_rows"}:
        raise ValueError("Answer contract permits only version, columns, min_rows and max_rows")
    if type(value.get("version", 1)) is not int or value.get("version", 1) != 1:
        raise ValueError("Answer contract version must be 1")
    columns = value.get("columns")
    if not isinstance(columns, list) or not 1 <= len(columns) <= MAX_QUERY_COLUMNS:
        raise ValueError(f"Answer contract requires 1..{MAX_QUERY_COLUMNS} ordered columns")
    normalized, names = [], set()
    for column in columns:
        if not isinstance(column, dict) or set(column) - {"name", "type", "nullable"}:
            raise ValueError("Contract columns permit only name, type and nullable")
        name, kind, nullable = column.get("name"), column.get("type"), column.get("nullable", False)
        if (not isinstance(name, str) or not 1 <= len(name) <= 128 or "\x00" in name
                or name in names or not isinstance(kind, str) or kind not in {"integer", "number", "string"}
                or type(nullable) is not bool):
            raise ValueError("Contract column names must be unique and types explicit")
        names.add(name)
        normalized.append({"name": name, "type": kind, "nullable": nullable})
    low, high = value.get("min_rows"), value.get("max_rows")
    if type(low) is not int or type(high) is not int or not 0 <= low <= high <= 200:
        raise ValueError("Answer contract row bounds must satisfy 0 <= min_rows <= max_rows <= 200")
    result = {"version": 1, "columns": normalized, "min_rows": low, "max_rows": high}
    if len(json.dumps(result, ensure_ascii=False).encode()) > 24000:
        raise ValueError("Answer contract exceeds 24000 bytes")
    return result


def contract_digest(contract):
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def role_finish_tool(legacy):
    result = copy.deepcopy(legacy)
    fn = result["function"]
    fn["description"] += (" Caller-contract mode: select one answer_evidence_id for answered/conditional; "
                          "list supporting_evidence_ids separately. Support never selects the answer.")
    props = fn["parameters"]["properties"]
    item = props["findings"]["items"]
    item["properties"].pop("evidence")
    item["required"] = ["text"]
    props["answer_evidence_id"] = {"type": "string"}
    props["supporting_evidence_ids"] = {"type": "array", "items": {"type": "string"}}
    fn["parameters"]["required"].append("supporting_evidence_ids")
    return result


def validate_finish_structure(args, schema):
    """Field-level feedback; role values are checked after remembering valid blockers."""
    def check(value, spec, field):
        kind = spec["type"]
        if kind == "object":
            if not isinstance(value, dict):
                reject("finish_argument_type", field, "Expected an object")
            unknown = set(value) - set(spec["properties"])
            if unknown:
                key = sorted(unknown)[0]
                reject("finish_argument_unknown", (field + "." if field else "") + key,
                       "This field is not accepted; the caller owns the answer contract")
            required = set(spec.get("required", [])) - ({"supporting_evidence_ids"} if not field else set())
            missing = required - set(value)
            if missing:
                reject("finish_argument_missing", (field + "." if field else "") + sorted(missing)[0],
                       "Required finish field is missing")
            for key, item in value.items():
                if not field and key in {"answer_evidence_id", "supporting_evidence_ids"}:
                    continue
                check(item, spec["properties"][key], (field + "." if field else "") + key)
        elif kind == "array":
            if not isinstance(value, list) or len(value) > 20:
                reject("finish_argument_type", field, "Expected an array of at most 20 items")
            for index, item in enumerate(value):
                check(item, spec["items"], f"{field}[{index}]")
        elif kind == "string" and (not isinstance(value, str) or len(value) > 8192):
            reject("finish_argument_type", field, "Expected a bounded string")
        if "enum" in spec and value not in spec["enum"]:
            reject("finish_argument_enum", field, "Value is outside the allowed enumeration")
    check(args, schema, "")


def validate_evidence_roles(args, results, names, contract):
    def source(ref, field, *, answer=False):
        if answer and isinstance(ref, list) and len(ref) > 1:
            reject("answer_reference_ambiguous", field, "Select one answer ID, not multiple candidate IDs")
        if not isinstance(ref, str) or not ref.strip() or len(ref) > 128:
            reject("answer_reference_required" if answer else "support_reference_invalid", field,
                   "Select one existing current-run evidence ID as a string")
        entry = results.get(ref)
        if not isinstance(entry, dict) or entry.get("ok") is not True:
            reject("answer_source_invalid" if answer else "support_source_invalid", field,
                   "Evidence must exist and be successful in this run")
        kind = names.get(ref)
        allowed = {"query"} if answer else {"query", "read_context", "inspect_schema", "analyze", "plot"}
        if kind not in allowed:
            reject("answer_source_type" if answer else "support_source_type", field,
                   "The evidence tool type is not allowed for this role")
        data = entry.get("data")
        if not isinstance(data, dict):
            reject("evidence_result_invalid", field, "Evidence result must be an object")
        if kind == "query":
            if data.get("truncated") is not False:
                reject("answer_truncated" if answer else "support_truncated", field,
                       "A query used as evidence must be complete and untruncated")
            if (not isinstance(data.get("rows"), list) or type(data.get("row_count")) is not int
                    or data["row_count"] != len(data["rows"])):
                reject("evidence_row_count_invalid", field, "Reported row count must match actual rows")
        return data

    answer = args.get("answer_evidence_id")
    if args["status"] in {"answered", "conditional"} or "answer_evidence_id" in args:
        data = source(answer, "answer_evidence_id", answer=True)
        columns = [column["name"] for column in contract["columns"]]
        if data.get("columns") != columns:
            reject("answer_columns_mismatch", "answer_evidence_id.columns", "Columns must match the caller contract in order")
        if not contract["min_rows"] <= len(data["rows"]) <= contract["max_rows"]:
            reject("answer_row_shape_mismatch", "answer_evidence_id.rows", "Row count is outside the caller contract bounds")
        for index, row in enumerate(data["rows"]):
            if not isinstance(row, dict) or set(row) != set(columns):
                reject("answer_row_shape_mismatch", f"answer_evidence_id.rows[{index}]", "Row keys must match contract columns")
            for col in contract["columns"]:
                value = row[col["name"]]
                if value is None and col["nullable"]:
                    continue
                finite_number = type(value) is int or type(value) is float and math.isfinite(value)
                valid = ((col["type"] == "string" and type(value) is str)
                         or (col["type"] == "number" and finite_number)
                         or (col["type"] == "integer" and finite_number
                             and (type(value) is int or value.is_integer())))
                if not valid:
                    reject("answer_value_type", f"answer_evidence_id.rows[{index}].{col['name']}",
                           "Value must have the declared type and nullability; booleans are not numeric counts")
    supports = args.get("supporting_evidence_ids")
    if not isinstance(supports, list) or len(supports) > 20:
        reject("support_references_invalid", "supporting_evidence_ids", "Provide an array of at most 20 support IDs")
    seen = set()
    for index, ref in enumerate(supports):
        field = f"supporting_evidence_ids[{index}]"
        source(ref, field)
        if ref in seen or ref == answer:
            reject("support_reference_duplicate", field, "Each supporting ID must be distinct from other supports and the answer")
        seen.add(ref)
    if answer is None and not supports:
        reject("support_reference_required", "supporting_evidence_ids", "Clarification without an answer must cite supporting context")
    return ([answer] if answer is not None else []) + supports
