# Changelog

## Unreleased — application-readiness work

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
- Ported the existing neutral-rate correction from
  `bdc6e6c140c850457da8dccd2e4045b715bf8eca`: generic counts use `successes` and
  `non_successes`, retain source columns and query evidence, and do not infer
  delivery semantics. Corresponding regressions are included.

Historical outputs are unchanged. This is local development work, not a published
release, new model experiment, favorable benchmark result or proof of adoption.
