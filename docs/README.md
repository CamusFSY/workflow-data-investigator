# Documentation

Start with the [repository quickstart](../README.md#quickstart), then inspect the
HTML report and run its `replay.py`. These guides are complete within this
repository; no separate project, account or historical experiment is required.

## Use the toolkit

| Goal | Guide |
| --- | --- |
| See expected outputs and reproduce each example | [Synthetic demo results](demo-output.md) |
| Look up commands, exit codes and troubleshooting | [CLI and Python API](../data-investigation-agent/README.md) |
| Describe and validate your CSV files | [Synthetic bundle format](../data-investigation-agent/docs/fixtures.md) |
| Prepare a reviewed public snapshot and separate factual scoring from replay | [Public-data provenance](../data-investigation-agent/docs/public-data.md) |
| Prepare one pinned public-data snapshot with caller-owned run controls | [WDI preparation guide](../data-investigation-agent/docs/wdi-smoke.md) |
| Supply a callback, configured client or recorded responses | [Provider integration](../data-investigation-agent/docs/provider-integration.md) |
| Separate the selected answer from supporting evidence and freeze its shape | [Answer evidence contract](../data-investigation-agent/docs/evidence-roles.md) |
| Understand the loop, tools and trust boundaries | [Architecture](architecture.md) |
| Understand which claims are supported by tests | [Evaluation and replay](evaluation.md) |
| Read the frozen live comparison, failures and limits | [Live evaluation](../data-investigation-agent/docs/live-evaluation.md) |
| Read the product technical report draft and build its PDF | [Technical report and source](research/technical-report/README.md) |
| Read the separate earlier clarification pilot and its limits | [Historical research overview](research/research-overview.md) |
| Update consumers of older rate fields | [Neutral-rate compatibility](../data-investigation-agent/docs/neutral-rate-compatibility.md) |

## Contribute and maintain

- [Contributing and testing](../CONTRIBUTING.md)
- [Security reporting and data handling](../SECURITY.md)
- [Roadmap](roadmap.md) and [changelog](../CHANGELOG.md)
- [Apache-2.0 license](../LICENSE) and [component notices](../THIRD_PARTY_NOTICES.md)
- [Source publication record and release checks](public-release.md)

The project is alpha. The supplied examples are synthetic and explicitly offline.
The source publication record identifies earlier commits; it is not a dependency
for installation, a package release or live model evidence.
