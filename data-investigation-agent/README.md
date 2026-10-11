# Data Investigation Agent

Read-only CSV/SQLite tools, an observable provider loop, and replayable evidence.
The included demonstrations use **synthetic data and an explicitly scripted
provider**. Runtime dependencies: Python 3.11+ standard library on Linux.

**License:** [Apache-2.0](LICENSE). **Status:** alpha; no package-index release.
This package guide includes the CLI, Python interface and troubleshooting.
The [bundle format](docs/fixtures.md) and [provider guide](docs/provider-integration.md)
are included in the source distribution, together with fixtures and examples.

## Quickstart

From this directory, without installing anything:

```sh
python3 -m investigator run \
  --fixture fixtures/join_multiplier \
  --out runs/my-join --inject-schema-error
python3 runs/my-join/replay.py
```

Open `runs/my-join/report.html`. Use a fresh output directory on every run; an
existing directory is never overwritten. The notebook is optional: its fixed
replay cells also work without Jupyter through `replay.py`.

To install the console command in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/data-investigator --help
.venv/bin/data-investigator --version
```

The wheel installs the tools, not development fixtures. Use a source checkout or
source distribution for `fixtures/`, or provide your own synthetic bundle.

## Commands

| Command | Behavior |
|---|---|
| `run --fixture DIR --out NEW_DIR` | Scripted demonstration using the included delivery vocabulary |
| `run ... --inject-schema-error` | Include a deliberate bad column, visible feedback and scripted correction |
| `inspect --fixture DIR --out NEW_DIR` | Import and inspect a declared synthetic bundle, without any provider |
| `validate --bundle DIR` | Check CSV files, schema, types and limits locally; JSON result, no provider |
| `investigate --bundle DIR --responses FILE --out NEW_DIR` | Execute explicit offline response bodies through real tools; no new model decisions |
| `replay DIR` | Verify a recorded run using the installed runtime |
| `python3 DIR/replay.py` | Use that run's bundled runtime; preferred for historical outputs |
| `run ... --mode live` | Stop with `LIVE_TRANSPORT_REQUIRED`; no credentials or model calls |

Exit codes: `0` means a recorded terminal status or successful replay; `1` means
investigation failure or failed replay verification; `2` means setup, input or
CLI misuse. **`needs_clarification` returns 0 but is not a completed investigation**:
check `status` and `investigation_complete` in `report.json`.

The defaults are 24 provider turns, 24 tool actions and 60 seconds. Each batch
contains at most four calls; `finish` must be alone. `--max-steps`,
`--max-tool-actions` and `--max-seconds` expose the bounded controls. The runtime
reserves a finalization opportunity and retains errors and unresolved questions.

## Python integration

```python
from investigator.loop import run

outcome = run(
    "Investigate the reported delivery-rate decline and return replayable evidence.",
    "my-synthetic-bundle",
    "new-evidence-directory",
    my_provider,
)
```

See the [provider contract](docs/provider-integration.md) for the exact call
signature; `run` uses positional names documented there. A provider chooses
registered tools and sees their actual feedback. The tools expose no shell,
network, arbitrary file-path reader or model-written Python executor.

Providers must expose `mode`, a printable `label`, and callable
`next(messages, tools, timeout_seconds)`. These are checked before input/output
side effects. `ChatCompletionsProvider` accepts your authorized callback and
requires explicit `allow_data_sharing=True`;
the caller still owns client configuration, retries, timeouts and costs.
The [public offline example](examples/recorded_investigation.py) and
[configured-client example](examples/configured_client.py) show both paths.
They are tested offline; no end-to-end live provider run is claimed.

| Tool | Use |
|---|---|
| `read_context` | Read named public documents |
| `inspect_schema` | Inspect imported tables, columns and types |
| `query` | Execute one bounded read-only SQLite query |
| `analyze` | Compare rates or group changes using fixed arithmetic |
| `plot` | Render up to 12 observed rates as SVG |
| `finish` | Return evidence references, questions and completion status |

Generic rate results use `successes`, `non_successes`, `source_columns` and
`source_evidence_id`. They do not infer “late” from an arbitrary complement.
[Compatibility details](docs/neutral-rate-compatibility.md) explain the change.
The tool contract cannot guarantee the truth of untyped prose or the authority
of a business definition.

## Fixtures, tests and troubleshooting

- [Fixture format and inspection](docs/fixtures.md)
- [Provider integration and trust boundary](docs/provider-integration.md)

```sh
python3 -B -m unittest discover -s tests -v
```

If installation imports another `investigator` module, create a fresh virtual
environment. If the output path exists, choose a new path; do not delete evidence
just to make the command succeed. A hash mismatch means replay integrity failed;
use the original unmodified bundle, and do not rewrite its manifest to silence
an error. Replaying an old bundle with a newer installed runtime may differ:
use its own `replay.py` instead.

A custom schema works with `inspect` and the tool API, but the demo's
`ScriptedMock` is intentionally tied to the delivery examples. `--mode live` is
not a hidden setup wizard: a trusted caller must supply a transport and its
authorization/cost controls through the Python API. No paid smoke run
is part of the installation or test suite.

Original development fixtures are synthetic and covered by [Apache-2.0](LICENSE).
For contributions and security reports, use this project's public
[contribution guide](https://github.com/CamusFSY/workflow-data-investigator/blob/main/CONTRIBUTING.md)
and [security policy](https://github.com/CamusFSY/workflow-data-investigator/blob/main/SECURITY.md).
The package is an early-stage toolkit, with no established adoption or
whole-answer accuracy claim.
