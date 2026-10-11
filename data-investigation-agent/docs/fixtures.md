# Your own synthetic CSV bundle

A bundle is a directory containing `catalog.json`, `metric_definition.md`,
`dashboard_query.sql`, `request.txt` and the CSV files explicitly named in the
catalog. The importer does not scan for extra data or evaluator answers. CSV
column names, types and table names must match the catalog; SQL identifiers are
validated by the importer.

For a small non-delivery example, copy `examples/simulation_bundle` into your own
directory, replace its CSV and update the catalog/metric/request together. Keep
`"synthetic": true` and describe how the data was generated. Do not relabel real
employer, patient or production data as synthetic.

Validate before choosing any provider:

```sh
# From data-investigation-agent/ with the installed CLI on PATH
data-investigator validate --bundle examples/simulation_bundle
```

Validation imports a temporary local SQLite snapshot and returns JSON with
table names, column types, row counts and original file hashes. It makes no
provider call and retains no output directory. Exit `0` means structurally valid;
exit `2` returns an `invalid` result with an error. A numeric conversion error
names the CSV, row and column without echoing the rejected cell value. This is
not a metric/authority check and cannot establish that a supplied description
is correct. No remote files are fetched and no SQL from the dashboard file is
executed during validation.

The existing importer limits still apply: up to 20 tables, 32 columns per table,
50,000 data rows per CSV, 4 MiB per CSV, 8 MiB total declared inputs and a 16 MiB
imported database. The four context documents are each limited to 64 KiB. Paths
must be flat declared filenames; linked/non-regular files are rejected. Empty
CSV cells become NULL; unspecified types default to TEXT. Declared INTEGER
values must fit SQLite's signed 64-bit range and REAL values must be finite.

Inspect the actual catalog and schema without selecting a provider:

```sh
# From data-investigation-agent/
python3 -m investigator inspect \
  --bundle examples/simulation_bundle --out runs/schema-check
```

The command writes a copied input snapshot, `input_manifest.json` and
`schema.json`. Its banner says **DATA LOAD ONLY**. Schema inspection is not a
successful investigation and does not validate metric semantics.

Use the [small catalog example](../examples/simulation_bundle/catalog.json) as the
format reference. `metric_definition.md` should identify the entity, numerator,
denominator, time basis, timezone, missing-value policy and any unresolved
business choices. The dashboard SQL is the observed calculation to investigate,
not an authoritative answer. Put the request in `request.txt` and pass the goal
explicitly when the caller needs different wording.

Three consumers have different scope:

- The importer, schema inspector and read-only query tools accept the declared
  synthetic schema within their bounds.
- `ScriptedMock` knows the delivery demonstration columns. For a new schema,
  write a transparent test provider or integrate an authorized model provider;
  do not interpret a scripted failure as measured model behavior.
- `RecordedProvider` executes explicitly supplied, fixed response bodies through
  the real tools. The public simulation recording exercises the complete
  import/query/analysis/report/replay path, including an actual SQL error and
  correction. It is hand-authored for that example, cannot assess an arbitrary
  metric definition, and makes no new model decisions. See the
  [working example and neutral provider adapter](provider-integration.md).

`missing_definition` deliberately lacks two business decisions. A useful
investigation retains that uncertainty and asks a specific question instead of
inferring approval from data patterns or a successful SQL query.
