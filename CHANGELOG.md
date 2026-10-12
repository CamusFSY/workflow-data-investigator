# Changelog

## Unreleased

- Preserve independently valid questions and assumptions when an optional-contract
  finish is rejected for an unrelated structural error. Reject contracts above the
  SQL worker's 64-column limit before provider or output setup. Keep arbitrary
  valid synthetic provenance replayable: compact artifact JSON within unchanged
  size caps and only index public-real snapshot IDs in the admission registry.
- Add an optional caller-frozen answer shape through the Python API, configured
  client and recorded CLI. Select one answer query separately from supporting
  evidence; preserve rejected attempts and the frozen contract in reports,
  notebooks and standalone replay. Shape acceptance does not prove numerical
  correctness; default legacy citations remain compatible.
- Add an offline preparation and explicit caller-admission recipe for one pinned
  World Bank WDI development snapshot, preserving raw provenance and keeping
  evaluation records outside model inputs. Expose the configured-client output
  token limit without changing its default or caller-owned spending controls.
- Prepare explicit public-real CSV provenance: source/license/attribution and
  exact snapshot hashes must match a reviewed code-owned allowlist, initially
  empty. Preserve data classification through reports, charts, notebooks and replay.
- Add opt-in `thinking="disabled"` request construction and configured-client
  `extra_body` mapping, without changing generic defaults, retries or accounting.
  Thinking-enabled tool histories remain unsupported; checks are offline only.
- Add a documentation index, reproducible synthetic output guide, architecture
  reference and repository badges for main CI, Apache-2.0, tested Python and alpha status.
- Make installation and compatibility guidance self-contained in this repository.
- Validate a developer's declared synthetic CSV bundle locally, with table/type/
  count feedback and actionable CSV conversion errors; no provider is selected.
- Add a provider-neutral callback adapter, explicit data-sharing opt-in and
  a complete configured-client example with caller-owned transport settings.
- Add a hand-authored offline response example for simulation pass rates. It
  executes real SQL, preserves an invalid-column error, computes changed counts
  and exports a report/notebook with standalone replay. It is not live evidence.
- Fix provider contract validation: missing `mode`, `label` or callable `next`
  now fails before bundle/output side effects. Snapshot mode/label so a later
  provider failure can still export partial evidence.
- Add bounded model/usage metadata and caller-reported/unknown dispatch status.
  `live_request_attempts` clarifies the existing `live_calls` attempts alias;
  the UI already described attempts. Neither field is audited billing.

### Initial toolkit

- Installable `workflow-data-investigator` package with `data-investigator`
  console entry point, help and version output; no runtime dependencies.
- Short product quickstart, fixture/provider documentation, contribution and
  security guidance, and offline GitHub Actions configuration.
- Installed-wheel smoke exercises all three synthetic demos away from the
  checkout, including the intentional SQL error and exported replay.
- Missing replay input and replay verification failures now have explicit CLI
  messages and exit codes instead of an unhandled traceback.
- Validate replay manifest container types before reading hash mappings, so
  malformed lists/null values produce a controlled verification error.
- Generic rate counts use `successes` and
  `non_successes`, retain source columns and query evidence, and do not infer
  delivery semantics. The complete [compatibility guide](data-investigation-agent/docs/neutral-rate-compatibility.md)
  and regression tests are included in this repository.

Changes under Unreleased have no published versioned release. Historical outputs
remain unchanged; offline checks are not new model experiments or adoption evidence.
