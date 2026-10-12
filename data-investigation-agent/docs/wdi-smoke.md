# One pinned WDI development smoke

This optional example prepares one fixed World Bank World Development Indicators
snapshot for a descriptive comparison. The repository includes the preparation
code and synthetic tests; the original data, source records and numerical
reference answers are not distributed here. No live model result is claimed.

## Preparation

Use Python 3.11+ on Linux and a separately obtained, compatible source package
with this layout:

```text
SOURCE_PACKAGE/
  LICENSE_DATA.md
  provenance/
    source_manifest.json
    raw/
      observations.json
      countries.json
      electricity_indicator.json
      population_indicator.json
```

The [preparation helper](../examples/prepare_wdi_smoke.py) lists the official
`SOURCE_URLS`, retrieval timestamps and exact `SOURCE_SHA256`, `RECORD_SHA256`
and `CSV_SHA256` pins. Each raw file's entry in `source_manifest.json` must record
its URL, byte count, SHA256, API response metadata (`api_header`) and actual
`retrieved_at_utc`. Retain the original data-license and attribution record in
`LICENSE_DATA.md`. All these files must match the pinned bytes.

A fresh API download may differ and cannot reproduce the original source or
license records from their hashes alone. Without the exact external files, this
specific snapshot example cannot run. Use the [synthetic quickstart](../README.md#quickstart)
to try the toolkit without external data. A different snapshot needs a separately
reviewed preparation recipe and [admission](public-data.md); do not edit data,
timestamps or hashes merely to bypass a mismatch.

From `data-investigation-agent/`, with the compatible source package available:

```sh
PYTHONPATH=. python3 examples/prepare_wdi_smoke.py \
  SOURCE_PACKAGE/provenance/raw NEW_PREPARATION_DIR
```

[The helper](../examples/prepare_wdi_smoke.py) uses no network, credentials,
model or gold. It checks four raw hashes, the original source/license record
hashes, one-page responses, both indicator IDs, the exact 18-country/2019–2023
scope, 90 unique matching keys per fact, one metadata row per country, no missing
values, positive integer population and access in [0,100]. Default JSON number
decoding, sorted rows, UTF-8 CSV and LF endings preserve original precision.
There is no rounding, imputation or deduplication. All three canonical CSV hashes
must match; drift fails before output and needs a separately reviewed snapshot.

Output separates model inputs from source and evaluation records:

- `bundle_inputs/` contains exactly catalog, metric definition, request,
  dashboard-note SQL and the three CSVs. It contains no expected answers.
- `provenance/` and `LICENSE_DATA.md` preserve original raw bytes, source manifest,
  original retrieval timestamps, URLs, source API metadata and attribution.
  These timestamps describe acquisition of the raw files, not this preparation.
  API response metadata is not HTTP response headers; no missing headers are invented.
- `admission_proposal.json` and `objective_contract.json` are host-only review
  and result-selection records. They are not model inputs or numerical gold.

Unique keys are verified against every row. The existing CSV importer does not
install SQLite primary-key constraints; the catalog's `verified_unique_key`
describes the checked data, not a physical constraint in the imported database.

Data are World Bank, World Development Indicators, **EG.ELC.ACCS.ZS** and
**SP.POP.TOTL**, under [CC BY 4.0 with World Bank additional terms](https://datacatalog.worldbank.org/public-licenses).
The glossary pages identify the licenses for
[electricity access](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/EG.ELC.ACCS.ZS)
and [population](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/SP.POP.TOTL).
Selection, renamed columns and derived calculations are attributed in the
bundle. Data licensing is separate from this code's Apache-2.0 license.

## Explicit caller admission and run controls

Preparation does not register a public snapshot. A trusted caller invokes this
fixed-snapshot `admit()` helper: it reconstructs from the pinned originals again,
compares all seven model-visible files, rejects extras or changed context, and
registers only the exact snapshot before ordinary bounded importer validation.
There is no model/CLI admission tool or general `allow_public` flag. The default
process registry is empty.

For a live integration, supply your own authorized transport, model and limits.
The transport must configure network timeouts, retries and cost controls; review
the data that may leave your host before setting `allow_data_sharing=True`.
This function defines an integration point and makes no call until you invoke it:

```python
from examples.prepare_wdi_smoke import GOAL, admit
from investigator.loop import run
from investigator.providers import ChatCompletionsProvider

def investigate_wdi(transport, *, model, raw_directory, bundle, output,
                    max_steps, max_tool_actions, max_seconds, max_output_tokens,
                    allow_data_sharing=False):
    provider = ChatCompletionsProvider(
        transport, model=model, allow_data_sharing=allow_data_sharing,
        thinking="disabled", max_output_tokens=max_output_tokens,
    )
    admit(raw_directory, bundle)
    return run(
        GOAL, bundle, output, provider, max_steps=max_steps,
        max_tool_actions=max_tool_actions, max_seconds=max_seconds,
    )
```

Choose explicit per-run limits within the [provider API bounds](provider-integration.md).
Provider turns include finalization; the deadline, a protocol failure or a
rejected finalization can stop a run before its configured maximum. Tool/action
limits, a context-byte ceiling and output-token settings do not establish a
monetary cap or an input-token guarantee. This example imposes no number of
funded runs and grants no permission to spend.

Keep your total budget and accounting in the application that owns the transport.
If a monetary ceiling is required, reserve a sound full-request worst-case cost
before dispatch, settle actual usage, and stop when the remaining budget cannot
cover another request. Disable SDK retries when each provider attempt must cause
at most one client invocation. For repeated runs, account for them cumulatively;
starting a new run directory does not reset the total budget. See the provider
guide for timeout, unknown-dispatch and caller-reported usage limitations.

## Objective and remaining validation

The model gets one question: compare the fixed sample's population-weighted
electricity access in 2021 and 2022, check grain/join keys, and cite a successful
SQL result returning one row with `baseline_year`, `comparison_year`,
`baseline_pct`, `comparison_pct`, `delta_pp`. Values are estimates; integer
count-rate analyze/plot tools are unsuitable. The tool sequence is not supplied.

Freeze independent Decimal gold outside `bundle_inputs` before live calls.
The selection contract requires exactly one matching successful SQL evidence
ID cited in final findings; missing/ambiguous references fail. Do not search
uncited intermediate queries to rescue a final answer. The predeclared absolute
tolerance is 1e-9 percentage points. This helper contains no numerical answers
or scorer. Keep this known development smoke out of held-out tasks.

The helper's `objective_contract.json` and example above use the legacy citation
interface. If you opt into an [answer contract](evidence-roles.md), freeze the
caller-owned shape and a selection policy using `answer_evidence_id` before the
first provider request. Check numerical values independently; shape acceptance
does not establish correctness. Preserve each experiment's original scoring
policy instead of reinterpreting earlier results.

Record the toolkit commit, source and input hashes, provider configuration,
limits and scoring policy before a run. Retain failures and use a fresh output
directory for every attempt. The saved trace, copied inputs and frozen runtime
can be checked without a provider:

```sh
python3 NEW_RUN_DIRECTORY/replay.py
```

The sample descriptor is not an official world aggregate; current region labels
are not historical classifications. A descriptive movement establishes neither
causation nor statistical significance. Replay checks executed operations and
does not establish free-text correctness or autonomous model success.
