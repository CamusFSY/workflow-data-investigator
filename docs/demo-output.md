# Synthetic demo results

These are descriptive results from the checked-in synthetic fixtures, executed
with the offline drivers. No model API was called. The SQL error, query results,
arithmetic and replay are real; the tool choices are scripted or hand-authored.
They are expected outputs for these examples, not an accuracy benchmark.

## Delivery examples

From the repository root after the [quickstart](../README.md#quickstart):

```sh
.venv/bin/data-investigator run \
  --fixture data-investigation-agent/fixtures/delivery_slip \
  --out runs/delay-demo
.venv/bin/python runs/delay-demo/replay.py
.venv/bin/data-investigator run \
  --fixture data-investigation-agent/fixtures/missing_definition \
  --out runs/clarification-demo
.venv/bin/python runs/clarification-demo/replay.py
```

Use a new output path for every run. The quickstart already runs the join example
with `--inject-schema-error`. All three reports display **SCRIPTED MOCK**.

| Fixture | Actual arithmetic or unresolved question | Recorded outcome |
| --- | --- | --- |
| [Join duplication](../data-investigation-agent/fixtures/join_multiplier/catalog.json) | Joined rows: 18/20 → 18/26. Distinct orders: 18/20 → 18/20. Current late-order joins: 8 rows from 2 orders. | `answered`, 14 actions with the injected SQL error |
| [Delivery delay](../data-investigation-agent/fixtures/delivery_slip/catalog.json) | Order grain: 18/20 → 12/20. North: 9/10 → 3/10; South: 9/10 → 9/10. | `answered`, 12 actions; localization does not prove cause |
| [Missing definition](../data-investigation-agent/fixtures/missing_definition/metric_definition.md) | Which date defines the week and its UTC bounds? Should cancelled orders be excluded? | `needs_clarification`, 3 actions; investigation remains incomplete |

For the join run, the trace preserves this sequence:

| Evidence | Actual tool feedback |
| --- | --- |
| `e005` | `query` fails: `no such column: promised_timestamp` |
| `e006` | `inspect_schema` returns the actual columns |
| `e007` | `query` succeeds using `promised_delivery_at_utc` |
| `e008` / `e010` | Joined-row and distinct-order aggregates differ |
| `e014` | `finish` cites the collected evidence |

Successful standalone replay prints:

```text
OFFLINE REPLAY VERIFIED: 14 tool results, including recorded SQL errors; 0 API calls.
```

The delay and clarification replays print 12 and 3 tool results respectively.
Counts apply to these exact fixture/driver options, not to arbitrary integrations.

## Custom simulation example

Follow [Use your own synthetic CSV](../README.md#use-your-own-synthetic-csv).
The [metric definition](../data-investigation-agent/examples/simulation_bundle/metric_definition.md)
counts passed and failed simulation runs and excludes cancelled runs. The
[response file](../data-investigation-agent/examples/simulation_responses.json)
is hand-authored and the report is labeled **OFFLINE RECORDED RESPONSES**.

The nine actions include a real `reporting_week` error at `e004`, schema inspection
at `e005`, a corrected `period_key` query at `e006`, and rate arithmetic at `e007`:
5/6 (83.3%) before versus 3/6 (50.0%) after, a -33.3 percentage-point change.
Changing a passed row to failed changes the computed result; it does not make
the fixed narration a new model diagnosis. The replay verifies all nine actions.

## Inspect a run

Open its `report.html` and expand the evidence steps. The adjacent `trace.jsonl`
contains the exact SQL and returns; `report.json` records mode and completion
state. `investigation.ipynb` replays the actual queries and fixed analysis through
saved events, with no invented execution output. `replay.py` includes a frozen
runtime and verifies copied-input hashes before comparing results.

These reports retain neutral `successes` and `non_successes` labels. Their
business interpretation depends on the supplied metric definition. See
[evaluation scope](evaluation.md) and [rate compatibility](../data-investigation-agent/docs/neutral-rate-compatibility.md).
