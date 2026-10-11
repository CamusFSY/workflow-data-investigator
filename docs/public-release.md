# Source publication and release checks

This repository contains the complete toolkit source, original synthetic fixtures,
tests, provider examples, documentation and Apache-2.0 license. Installation and
offline reproduction require no other repository. Start with the
[quickstart](../README.md#quickstart) or [documentation index](README.md).

## Initial source publication

The source was first published on 2026-10-11 in commit
[`152dc5f3eb6911a99dde391075a1a26963b15d30`](https://github.com/CamusFSY/workflow-data-investigator/commit/152dc5f3eb6911a99dde391075a1a26963b15d30).
This was a source publication, not a versioned GitHub Release or package-index upload.
The repository began with its own Git history. Its initial 83 source paths were
read back and reconciled with the exported snapshot.

The initial source-set SHA-256 is
`8c977ded1d2f6bf0cb36b1c02f87dde7c37ce64a4754afd7f225890b85908975`.
It hashes UTF-8 lines of `SHA256 + two spaces + path + LF`, sorted by path.
The initial source ZIP SHA-256 is
`b82b32c41c744a1fd2baf39860feaec5069ab6c7eafd1f9ae150902f0ad9e92d`.
These are historical identifiers for that initial snapshot, not checksums for
later source trees or current build archives.

The initial commit's [hosted check](https://github.com/CamusFSY/workflow-data-investigator/actions/runs/38140217002)
passed 77 tests on Python 3.11 and 3.12, built wheel/sdist artifacts and exercised
the installed package. Its three synthetic examples replayed 14, 12 and 3 actions,
including recorded SQL errors, with zero model calls. For any later change,
inspect its exact commit and conclusion in the [workflow runs](https://github.com/CamusFSY/workflow-data-investigator/actions/workflows/ci.yml).
The README badge tracks `main`, not an unmerged branch or a live model evaluation.

## Preparing a release

1. Choose the exact source commit and run the tests, build and installed-wheel
   checks in [CONTRIBUTING.md](../CONTRIBUTING.md).
2. Inspect the source and distribution file lists. Include only intended code,
   original synthetic inputs, documentation, license and packaging metadata.
   Exclude credentials, authorization records, external datasets and raw model traces.
3. Review contribution rights and retain the notices for shipped materials.
   [Component notices](../THIRD_PARTY_NOTICES.md) and [SECURITY.md](../SECURITY.md)
   describe the current license and data-handling boundaries.
4. Record artifact hashes and observed results for that exact commit. Keep new
   evidence in a new directory and preserve existing bundles' frozen replay code.
5. Publish versioned release notes only when a release actually exists, distinguishing
   offline checks from any separately authorized live evaluation.

Successful tests, hash checks and source publication establish neither metric
truth, ownership of every future contribution, model autonomy nor external adoption.
