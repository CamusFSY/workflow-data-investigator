# Security and responsible reporting

This is an early-stage local toolkit. Its security and regression checks use
synthetic data; the separate [public-data live evaluation](data-investigation-agent/docs/live-evaluation.md)
is not a security audit. It is not a hostile-code sandbox or a production
data-governance system. No stable release support or security-response SLA is
currently claimed.

## Report privately

A private vulnerability intake or security mailbox has not been verified for
this project. To request a private channel, open a minimal
[issue in this repository](https://github.com/CamusFSY/workflow-data-investigator/issues/new)
titled **Private security contact requested**, containing no exploit details,
credentials, personal data or raw trace. Wait for the maintainer to confirm a
private reporting channel before sharing a synthetic reproduction or sensitive
details. This policy does not claim that GitHub private reporting is enabled.

## Trust boundary

The importer reads declared local CSV files into a bounded SQLite snapshot. SQL
uses a read-only connection, authorizer and resource limits. Tools expose neither
arbitrary Python execution nor a shell. Exported notebooks contain fixed replay
templates; provider values are data. Reports escape provider-supplied text.

The host Python process, supplied provider transport and trusted clarification
callback are trusted. A malicious host or callback is outside the boundary.
The callback/transport owns external timeouts, credentials, authorization and
cost accounting. The offline CLI does not configure those services.

The neutral provider adapter requires explicit `allow_data_sharing=True` before
using a supplied transport. Context documents, schema, SQL text, returned rows
and prior conversation may then reach the caller's configured endpoint. This is
not an anonymization layer. A callback/client may retry or bill after a timeout;
attempt limits and returned token usage do not establish a monetary ceiling.
Transport dispatch receipts are caller-reported, not independently audited.

Generated bundles include copied inputs, SQL, returned rows and public tool
notes. Review them before sharing. Input hashing detects accidental changes; it
does not authenticate a maintainer, prove source authority or establish factual
correctness. Do not run a downloaded replay script or notebook from an unknown
author solely because it contains a manifest.

Use the included synthetic fixtures. Do not point the demo at employer, patient,
credential or production data. Follow [public-release guidance](docs/public-release.md)
before changing repository visibility or publishing an archive.
