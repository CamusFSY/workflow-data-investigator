# Contributing

Start with a reproducible bug, a small synthetic fixture or a documentation fix.
The Python package is in `data-investigation-agent/`; the
[documentation index](docs/README.md) maps the CLI, bundle and provider guides.

## Report a bug or propose a change

Use this repository's [issue forms](https://github.com/CamusFSY/workflow-data-investigator/issues/new/choose)
for a reproducible bug or concrete use case. Include the source commit, Python
version, OS, exact command, expected and actual behavior, and a small synthetic
input. State whether the provider was scripted, recorded or model-driven.
Redact credentials and sensitive data. For vulnerabilities, follow
[SECURITY.md](SECURITY.md) instead of posting exploit details publicly.

Open changes through this repository's [pull requests](https://github.com/CamusFSY/workflow-data-investigator/pulls).
Explain one concrete problem and the resulting behavior. Include the commands
actually run and any checks not run. Add a focused regression when changing
runtime, protocol, filesystem or replay behavior; documentation fixes should
check links, examples and affected packaging.

## Local checks

Runtime and offline tests use Python's standard library on Linux:

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

Build dependencies may be downloaded by these installation commands. The tests
and packaging smoke make no model calls. The smoke imports the installed package
from a temporary directory, replays all three delivery cases and the custom
simulation example, and executes the public callback/client examples with offline
doubles. It checks actual status, error feedback and replay results.

The [CI workflow](.github/workflows/ci.yml) runs tests, builds and installed-wheel
checks on Python 3.11 and 3.12. Inspect the exact commit in
[hosted runs](https://github.com/CamusFSY/workflow-data-investigator/actions/workflows/ci.yml)
when reviewing a change; a previous successful run does not certify a later one.

## Contribution boundaries

- Keep generic analysis labels neutral. Arithmetic does not prove metric meaning,
  business approval or the truth of a provider's explanation.
- Keep providers separate from tools. Offline commands must not discover credentials,
  call a paid model, retry a network request or create a spending ledger.
- Preserve previous evidence bundles. New checks use new output directories with
  their own input and runtime provenance.
- Use original synthetic reproductions and document their origin and licensing.
  Never copy private evaluator answers into model-visible inputs.
- Describe AI assistance and what was actually verified. AI review is not
  independent human review. Do not manufacture reports of use or adoption.

Maintainers reproduce issues, review changes and update [CHANGELOG.md](CHANGELOG.md)
with user-facing behavior. Build a release from its exact reviewed source commit
using the [release checks](docs/public-release.md#preparing-a-release). Contributions
must be compatible with the project's [Apache-2.0 license](LICENSE); retain
applicable attribution and third-party notices.
