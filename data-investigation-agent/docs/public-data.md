# Explicit public-data snapshots

This is a local preparation interface.
`investigator.provenance.PUBLIC_SNAPSHOTS` starts empty. The admission unit tests
use synthetic test doubles, not a real-data benchmark. Existing synthetic bundles
continue to use their original declarations. Never mark real data synthetic.
The [fixed WDI recipe](wdi-smoke.md) prepares one pinned development snapshot
from verified original source bytes and permits a trusted caller to admit only
those exact reconstructed files. It does not enable arbitrary public inputs.

## Admission contract

Public inputs use the same bounded flat CSV bundle layout: `catalog.json`,
`metric_definition.md`, `dashboard_query.sql`, `request.txt`, and declared CSVs.
Only those files become model-visible input. The runtime does not download,
unpack archives, execute supplied scripts, or accept arbitrary SQLite files.
The existing 4 MiB/file, 8 MiB total, 50,000 rows/CSV, 20 tables, 32 columns/table
and 16 MiB imported-database limits remain in force.

The catalog must explicitly contain `"synthetic": false` and a `provenance`
object with exactly these fields:

```json
{
  "type": "public-real",
  "dataset_id": "reviewed-dataset-id",
  "snapshot_id": "reviewed-snapshot-id",
  "source_url": "https://publisher.example/dataset",
  "license_id": "CC-BY-4.0",
  "license_url": "https://publisher.example/license",
  "retrieved_at": "2026-10-11T00:00:00Z",
  "upstream_sha256": "<64 lowercase hex digits identifying the source bytes>",
  "transformation": "Describe extraction/filtering, source version, preparation script hash and any type conversion.",
  "attribution": "Publisher, dataset title, source and license attribution; describe modifications.",
  "personal_data": false,
  "sensitive_data": false,
  "private_data": false
}
```

The example is a schema illustration, not an approved dataset. One reviewed entry
in `PUBLIC_SNAPSHOTS`, keyed by `snapshot_id`, must have exactly:

```python
{
    "provenance": { ... },  # exact catalog declaration above
    "files": {"catalog.json": "<sha256>", ...},  # every context/CSV file, no wildcard
    "review_reference": "Source/license/privacy review and immutable snapshot identity",
}
```

Admission first rejects an unknown declaration before reading the other bundle
files. It then compares the complete file set and every SHA256 before creating
output or invoking the provider. Merely writing `public-real` or a license name
inside a catalog cannot authorize it. There is no CLI flag, model tool, bundle
allowlist file or `run()` option that approves a new snapshot.

The maintainer must inspect actual source bytes and a reproducible preparation
recipe before adding an entry. Record the immutable upstream version and URL,
actual downloaded SHA256, license/attribution, excluded domains/columns and
privacy review. For multiple official source files, `upstream_sha256` may pin a
separate canonical source manifest containing their URLs and individual hashes;
the transformation record must explain this convention and retain those raw
snapshots outside the model bundle. Do not put gold, scoring SQL, task answers,
credentials, private logs or evaluation-selection notes into any admitted file.

The registry is trusted application code, not a privacy classifier or a legal
certification. False declarations in a synthetic bundle are not detected by a
hash check. A trusted host can modify the program. Public admission only means
that these exact bytes match the locally reviewed entry; it is not approval of
metric meaning, a production guarantee or permission to transmit to any endpoint.
External transmission still needs the caller's explicit `allow_data_sharing=True`.

## Provenance and replay

Validation and import return `synthetic` plus a structured `provenance` record.
The original catalog and CSV bytes remain unchanged. The run manifest and JSON
report retain the full declaration, frozen approval, file hashes and catalog
hash. Each trace event identifies its data type, snapshot ID and catalog hash.
The system prompt, HTML report, notebook and SVG use the actual classification;
public snapshots are never labeled synthetic. SVG metadata also retains the
provenance record.

Replay rechecks copied bytes and the frozen admission record, even when the
current allowlist no longer contains the snapshot. It does **not** renew the
source/license/privacy review or authenticate unsigned artifacts. A person who
rewrites all artifacts and hashes can manufacture a different bundle; hashes
are consistency checks, not signatures. Run the supplied frozen `replay.py` to
preserve the behavior of historical runs.

## Preparing an external evaluation

Dataset bytes, license notices and gold have separate provenance from this
Apache-2.0 code. Retain source attribution and applicable data-license notices;
do not copy unlicensed benchmark evaluator code into this repository. No dataset
or third-party evaluator is distributed by this preparation change.

Before held-out calls, freeze a separate task/gold manifest with dataset snapshot
hashes, task IDs, goals, expected result schemas, SQL-result selection policy,
row-order/duplicate semantics, numeric tolerances and the two agent configurations.
Keep it outside model-visible bundles and frozen replay directories. Development
smoke questions and their known answers must be disjoint from held-out tasks.
Do not choose a successful query after looking at gold or silently replace failed
tasks. Record errors, missing evidence and truncated outputs as separate outcomes.

Replay success is an engineering reliability metric. `finish` currently provides
free text and evidence IDs; it does not validate factual/prose correctness.
Structured numerical claims are deferred. Score a predeclared, unambiguous
query-result reference independently, and report ambiguous/missing references
instead of treating any matching intermediate query as a correct answer.

For BIRD-like SQL tasks, a separately named multiset/order-aware comparison can
preserve duplicates and task-required order. Do not call it the official BIRD
score or imply that a small selected subset establishes benchmark performance.
The original SQLite archive, source version, all selected tables and row-level
privacy still need inspection. A CSV conversion must preserve SQLite values,
NULLs and relevant query semantics, fit the existing bounds, and be recorded;
this runtime has no direct BIRD SQLite importer.

For WDI-like public aggregates, use read-only SQL and separately implemented
Decimal checks with a frozen tolerance. Continuous percentages and population
estimates are not integer success/total observations and must not be rounded
into `analyze`/`plot` inputs. Missing values remain unknown. National rows and
aggregate rows must not be double-counted; a weighted descriptor of a selected
country set is not the publisher's world aggregate.

Paid calls, dispatch authorization, cost accounting, price assumptions and
retry policy belong to your application. This project does not create or
reset a spending ledger, and these offline checks grant no live permission.
