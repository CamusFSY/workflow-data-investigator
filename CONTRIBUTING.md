# Contributing

Start with a reproducible bug, a small synthetic fixture or a documentation fix.
The maintained entry point is `data-investigation-agent/`.
The public repository is
[CamusFSY/workflow-data-investigator](https://github.com/CamusFSY/workflow-data-investigator).
See [publication evidence](docs/public-release.md) for the initial source commit
and verified hosted checks.

## Local checks

The investigator's runtime and tests use Python's standard library on Linux:

```sh
cd data-investigation-agent
python3 -B -m unittest discover -s tests -v
```

To check packaging, from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'build>=1.2,<2'
.venv/bin/python -m build data-investigation-agent --outdir dist/investigator
python3 -m venv .venv-wheel
.venv-wheel/bin/python -m pip install --no-deps dist/investigator/*.whl
python3 scripts/smoke_distribution.py --python .venv-wheel/bin/python
```

The packaging smoke uses an unrelated temporary working directory, the installed
entry point and all three demo fixtures. It checks actual output statuses and
offline replay, including the deliberate SQL error. It never calls a model.

The CI workflow runs the investigator tests, package build and installed-wheel
smoke on pushes and pull requests. The
[initial hosted run](https://github.com/CamusFSY/workflow-data-investigator/actions/runs/38140217002)
passed on Python 3.11 and 3.12. Check the run's commit SHA when evaluating a later
change; the initial result applies to the initial published source.

## Change scope

- Explain one concrete problem and its before/after behavior. Add a focused test
  when changing runtime, protocol, filesystem or replay behavior.
- Keep generic analysis labels neutral. A numerator is not automatically an
  on-time delivery count; numerical consistency does not prove a business claim.
- Keep providers separate from tools. Do not add a hidden API call, automatic
  credential discovery, paid retry or budget reset to an offline command.
- Preserve previous evidence bundles. New evidence belongs in a new directory
  with its own provenance, not over an old result. Historical research and raw
  model runs are outside this product distribution.
- Use synthetic data for reproductions. Include fixture origin and licensing.
  Do not inspect or copy private evaluator answers into model-visible inputs.
- AI-assisted patches are welcome; describe what was actually checked. Do not
  describe AI review as independent human review.

## Maintainer workflow

Triage real user reports, reproduce them, review the diff and test outcome, and
record user-facing behavior changes in `CHANGELOG.md`. A release should be built
and smoke-tested from its exact source commit. Do not manufacture issues, stars,
downloads or releases as evidence of adoption. Public-release scope and access
remain separate maintainer decisions; see [release guidance](docs/public-release.md).
