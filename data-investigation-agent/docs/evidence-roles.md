# Optional caller-frozen answer contract

This explicit caller option separates **one selected answer query** from any supporting
queries, context, schema inspection, analysis or plots. It checks source, result
shape and value types. It does not decide whether the selected numerical answer
is correct, whether support is relevant, or whether prose follows from evidence.

The trusted caller supplies the public shape before the first provider request:

```python
outcome = run(
    goal, bundle_directory, new_output_directory, authorized_provider,
    max_steps=8, max_tool_actions=24,
    answer_contract={
        "version": 1,
        "columns": [{"name": "order_count", "type": "integer", "nullable": False}],
        "min_rows": 1,
        "max_rows": 1,
    },
)
```

This example sets no new permission or spending limit. The caller still owns
authorization and transport. A contract contains no expected values or reference
SQL. Neither model output, the request document, catalog metadata nor an earlier
query can define, enable or replace this option. The runtime validates and copies
the caller object; later changes to that original object do not alter the run.

The version-1 contract has exactly these fields (version defaults to 1):

| Field | Meaning |
|---|---|
| `columns` | 1..100 unique named columns in exact output order |
| Column `type` | `integer`, `number` or `string` |
| Column `nullable` | Boolean; defaults to false |
| `min_rows`, `max_rows` | Required integers; `0 <= min_rows <= max_rows <= 200` |

Every actual row must have exactly those column names. `integer` accepts Python
integers and finite integral floats returned by SQLite; `number` accepts finite
integers/floats. Booleans are not numeric values. Strings and SQL NULL remain
distinct; NULL is allowed only for a nullable column. Row bounds do not define
ordering, distinctness, ranking semantics, filtering or expected numerical values.
The independent evaluator must check these when the task requires them.

## Recorded CLI and configured client

From `data-investigation-agent/`, run the separate hand-authored role example:

```sh
python3 -m investigator investigate \
  --bundle examples/simulation_bundle \
  --responses examples/simulation_role_responses.json \
  --answer-contract examples/simulation_answer_contract.json \
  --out runs/simulation-roles
python3 runs/simulation-roles/replay.py
```

This makes zero model calls. It preserves the intentional SQL error, selects
query `e006` as the answer and lists `e002`, `e003`, `e007`, `e008` as supports.
The original simulation recording is unchanged and uses the legacy interface.
The new recording has fixed actions and narration; it cannot choose a correction
for new data. The contract describes two rows of period/count columns, with no
expected counts. Check the actual values separately.

The CLI reads only the explicitly selected JSON file, before loading the
recording or creating output. Files are limited to 24000 bytes and must be
regular, unlinked files beneath a path with no symlinks. Invalid JSON, `null`,
unknown fields or invalid shape metadata produce setup error exit code 2.
Omitting the flag keeps the existing CLI behavior. The delivery-specific
`run` command remains a legacy scripted demo.

Python callers may use `investigator.evidence.load_answer_contract(path)` to
read the same format. Pass the result as `answer_contract=` to `run()`,
`examples/configured_client.py`'s `investigate_with_client()`, or the callback
examples in [provider integration](provider-integration.md). Existing thinking,
token, turn, timeout and caller-owned spending settings are unchanged. The SDK
wrapper is tested with an offline double; no live performance gain is claimed.

## Finish in contract mode

```json
{
  "status": "answered",
  "summary": "The selected query contains the measured count.",
  "findings": [{"text": "A separate grain check supports interpretation."}],
  "answer_evidence_id": "e003",
  "supporting_evidence_ids": ["e001", "e002", "e004"],
  "questions": []
}
```

`answer_evidence_id` must name one successful, untruncated `query` result from
the current run, matching the frozen contract. The runtime never selects the
first, last or best-looking query. Multiple answer IDs, missing IDs, unknown IDs,
unsuccessful results and context-as-answer are rejected.

`supporting_evidence_ids` is required, may be empty, and allows up to 20 distinct
successful current-run evidence IDs. A support may be a query, context read,
schema inspection, analysis or plot. Supporting queries must also be complete;
they do not have to match the answer's shape. An answer ID cannot be repeated as
support. Analysis/plot retain the existing complete-query source requirement.
These checks establish referenced sources, not the relevance of a support or
truth of a statement such as “matching totals prove all categories were retained.”

`answered` and `conditional` require an answer ID. `needs_clarification` may omit
it if at least one supporting source and a specific unresolved question or
assumption are present. If an answer ID is supplied, it is validated normally.
The existing persistent question/assumption and trusted clarification rules
remain in effect. Findings contain `text` only in this mode; the old untyped
`findings[].evidence` arrays are rejected to avoid two competing citation schemes.

## Rejection, budgets and artifacts

Contract and role errors return `error.code`, `error.field` and `error.message`
as an ordinary tool observation. A validly encoded rejected finish uses one tool
action. During a normal turn, a later provider turn can correct it within the
original limits. Once `finish_only` is true, any rejected finish ends the run;
there is no additional provider request or budget extension. Invalid JSON or
invalid tool-call envelopes still terminate under the existing protocol rules.

`report.json`, `report.html` and the notebook show the selected answer, separate
supports, normalized contract and its canonical SHA-256. Source provenance stays
attached to the run and events. `answer_contract.json` is separately frozen and
hashed in `manifest.json`. Its file hash includes presentation formatting; it is
distinct from the canonical contract hash in the report.

The bundled `replay.py` restores that contract, re-executes the recorded tools,
checks the same role/type/shape results, and prints the accepted roles and source
provenance. Rejected attempts stay in the trace. Replay checks integrity relative
to the supplied manifest; it does not authenticate a replaced manifest or decide
numerical correctness, source authority or causal claims. A fresh synthetic
CSV-based oracle in the tests deliberately rejects a selected count of 999 even
though the interface accepts its valid one-row integer shape.

## Compatibility

Omit `answer_contract` (or the CLI flag) to keep the original tool schema, prompt
and multi-reference finish behavior. Existing recordings use that legacy mode. Historical
bundles keep their original frozen replay runtime. This option changes the tool
and prompt contract only for explicitly opted-in calls. Review the changed
payload and its data-sharing and cost authorization before a live request;
approval for a different configuration does not automatically cover this one.

No existing scorer or completed experiment is reinterpreted by this change. The
historical results keep their original scoring contracts. The fresh offline tests
establish interface behavior and compatibility, not improved live accuracy or a
successful autonomous model correction.
