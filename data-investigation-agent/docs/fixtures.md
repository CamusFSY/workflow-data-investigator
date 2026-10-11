# Synthetic fixture format

A bundle is a directory containing `catalog.json`, `metric_definition.md`,
`dashboard_query.sql`, `request.txt` and the CSV files explicitly named in the
catalog. The importer does not scan for extra data or evaluator answers. CSV
column names, types and table names must match the catalog; SQL identifiers are
validated by the importer.

Start by copying one of `fixtures/join_multiplier`, `fixtures/delivery_slip` or
`fixtures/missing_definition` into a new development directory. Keep
`"synthetic": true` and describe how the data was generated. Do not relabel real
employer, patient or production data as synthetic.

Inspect the actual catalog and schema without selecting a provider:

```sh
# From data-investigation-agent/
python3 -m investigator inspect --fixture fixtures/delivery_slip --out runs/schema-check
```

The command writes a copied input snapshot, `input_manifest.json` and
`schema.json`. Its banner says **DATA LOAD ONLY**. Schema inspection is not a
successful investigation and does not validate metric semantics.

Use the existing [catalog example](../fixtures/delivery_slip/catalog.json) as the
format reference. `metric_definition.md` should identify the entity, numerator,
denominator, time basis, timezone, missing-value policy and any unresolved
business choices. The dashboard SQL is the observed calculation to investigate,
not an authoritative answer. Put the request in `request.txt` and pass the goal
explicitly when the caller needs different wording.

Two consumers have different scope:

- The importer, schema inspector and read-only query tools accept the declared
  synthetic schema within their bounds.
- `ScriptedMock` knows the delivery demonstration columns. For a new schema,
  write a transparent test provider or integrate an authorized model provider;
  do not interpret a scripted failure as measured model behavior.

`missing_definition` deliberately lacks two business decisions. A useful
investigation retains that uncertainty and asks a specific question instead of
inferring approval from data patterns or a successful SQL query.
