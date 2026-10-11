# Security and responsible reporting

This is an early-stage local toolkit, tested with synthetic data. It is not a
hostile-code sandbox or a production data-governance system. No stable release
support or security-response SLA is currently claimed.

## Report privately

If the repository's **Security → Report a vulnerability** option is enabled,
use it to send a minimal synthetic reproduction to the maintainer. Its current
availability must be checked; this document does not assert that it is enabled.

If that option is absent, open an issue titled **Private security contact
requested**, containing no exploit details, credentials, personal data or raw
trace. Wait for a private reporting channel before sharing sensitive details.
No separate security mailbox is currently documented.

## Trust boundary

The importer reads declared local CSV files into a bounded SQLite snapshot. SQL
uses a read-only connection, authorizer and resource limits. Tools expose neither
arbitrary Python execution nor a shell. Exported notebooks contain fixed replay
templates; provider values are data. Reports escape provider-supplied text.

The host Python process, supplied provider transport and trusted clarification
callback are trusted. A malicious host or callback is outside the boundary.
The callback/transport owns external timeouts, credentials, authorization and
cost accounting. The offline CLI does not configure those services.

Generated bundles include copied inputs, SQL, returned rows and public tool
notes. Review them before sharing. Input hashing detects accidental changes; it
does not authenticate a maintainer, prove source authority or establish factual
correctness. Do not run a downloaded replay script or notebook from an unknown
author solely because it contains a manifest.

Use the included synthetic fixtures. Do not point the demo at employer, patient,
credential or production data. Follow [public-release guidance](docs/public-release.md)
before changing repository visibility or publishing an archive.
