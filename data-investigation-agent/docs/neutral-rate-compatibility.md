# Neutral rate output compatibility note

This is a narrow offline correction to generic arithmetic and presentation. It is
not a typed metric implementation or a claim that qualified model answers are now
correct. It does not require a model request, private answer, credential or budget
ledger. Historical model runs and private research are outside this distribution.

The included synthetic
[rate-meaning fixture](../tests/fixtures/rate_meaning/rate_samples.csv) contains
generic aggregate counts. For example, treating `completed / total` as a rate
does not make the numerator an on-time delivery count or the complement a late
delivery count. The same arithmetic can describe several business concepts;
the selected columns and evidence must remain visible.

The [regression tests](../tests/test_rate_semantics.py) use these small local
aggregates to check neutral output names, source binding and rendering. They do
not require any historical report or answer key. Existing evidence bundles must
retain their original frozen runtime and results.

## Output changes

| Old output | New output | Meaning |
| --- | --- | --- |
| `baseline/current.on_time` | `baseline/current.successes` | Count selected by the `successes` argument; not a business approval. |
| `baseline/current.late` | `baseline/current.non_successes` | `total - successes`; may include cancellations, open records or other categories. |
| `late_count_change` | `non_success_count_change` | Change in that arithmetic complement. |
| `plot.points[].on_time` | `plot.points[].successes` | Same selected count, without inferred metric meaning. |
| No plot complement | `plot.points[].non_successes` | Arithmetic complement, with no inferred late label. |
| Hard-coded on-time chart title/alt | Untyped ratio title/alt, source-column caption | Names the calculation and its selected columns. |

The same neutral count fields apply within `cohort_change.groups[]`. Ratios,
count arithmetic, period selection, group ordering and query execution are
unchanged. The following metadata accompanies analysis and plots:

```json
{
  "rate_semantics": "untyped_ratio",
  "source_columns": {
    "successes": "completed",
    "total": "total",
    "period": "period"
  },
  "source_evidence_id": "source"
}
```

`period` is replaced by `label` for plots; cohort analysis also records `group`.
These are exact **query-result column bindings**, not proof of a physical source
predicate or approved metric. The evidence ID points to the successful query
event containing the actual SQL and rows; the frozen input/runtime manifest
supplies the rest of the reproducible provenance. SQL aliases can be identical
for different queries, so evidence IDs must not be discarded or equated because
two ratios happen to match. Existing outer event/tool-call IDs are unchanged.

There is no validated metric type in the current runtime. All generic outputs
therefore remain untyped, including when an input column is named `on_time` or a
catalog description says approved. No optional model-provided label or
`metric_contract` field can promote the output. Typed-measurement research remains
on separate candidate branches; this product branch does not enable that API.

## Callers, rendering and old bundles

This is an intentional **output-key change**: no misleading legacy aliases are
retained. Update consumers of `on_time`, `late` and `late_count_change` from generic
analytics. The local scripted mock and its count assertion are updated. Genuine
SQL source columns with those names remain untouched in query results and
provenance; they do not grant type validation.

Tool names, argument schemas, provider/transport signatures, finish states,
clarification rules, SQL limits and budgets are unchanged. Analyze/plot **tool
descriptions** now explain neutral arithmetic; consequently the full tools JSON,
initial payload and source hashes change. The parent's exact product/tool/payload
pins need review before any separately authorized live run. The lone finish
schema is unchanged. This patch neither updates those pins nor creates a run or
spending authorization.

Report charts and notebook outputs use the actual neutral tool results. Export
templates identify provider-written prose separately and state that metric
meaning, causal claims and business approval are not arithmetically verified.
They do not rewrite the model's prose or certify it through a `conditional` flag.
`report.json` continues to preserve the provider's answer, while its cited trace
holds the measured outputs; consumers must not treat the answer text as a typed
rate claim.

Replay an old bundle with **that bundle's own `replay.py` and frozen `_replay`**.
It correctly reproduces the old misleading labels as historical evidence. Do not
replace its runtime, regenerate its report with the new exporter, or accept a
comparison mismatch as a migration. Current `investigator.replay` uses current
semantics and will not silently convert an older trace. New bundles freeze the
corrected runtime and replay the new neutral fields exactly.

Offline regression command, from `data-investigation-agent/`:

```bash
python -m unittest discover -s tests -p test_rate_semantics.py -v
python -m unittest discover -s tests -v
```

The targeted fixtures distinguish 8/10 -> 5/10 completions from 6/10 -> 3/10
timely counts; verify cancellations within the complement; and compare equal
0.5 -> 0.75 ratios from 8/16 -> 12/16 versus 4/8 -> 9/12. Tests check real SQL,
source bindings/IDs, cohorts, escaped SVG, report captions, recorded notebook
events, execution of trusted notebook-template cells, and standalone offline
replay. All providers in these tests are explicitly SCRIPTED.
