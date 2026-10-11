# Component provenance and third-party notices

This local product candidate contains the investigator tools, their tests,
documentation and original synthetic development fixtures. The project source
and original fixture files are distributed under the accompanying Apache-2.0
[LICENSE](LICENSE). The package carries the same complete license text.

## Included code and data

The investigator uses Python's standard library, including its SQLite interface.
No third-party Python package, SQLite library, browser, font, media asset or
external dataset is vendored in the source, wheel or source distribution.
Installed Python and SQLite implementations retain their own upstream licenses;
this project license does not replace those licenses.

The delivery fixtures are synthetic and their generator is included at
`data-investigation-agent/fixtures/build_dev.py`. The two small test fixture
directories are synthetic regression inputs. None represents employer, patient
or production data. The catalog declarations and test descriptions record their
intended use; a synthetic label must not be applied to real data supplied later.

Builds use the separately installed `build`, `setuptools` and `wheel` packages.
The optional hosted workflow references GitHub's checkout and setup-python
actions by fixed revisions. These tools are not copied into this distribution
and remain subject to their own upstream terms. Runtime and offline tests need
only the standard library.

## Explicitly excluded material

This candidate includes no legacy research package, upstream task/checker copy,
external CDN cache, prior model-run bundle, uploaded document or media archive.
In particular, MCPMark task/checker copies and separate MCPMark CDN fixtures are
absent. No redistribution rights to those excluded CDN inputs are asserted.

The proposed GitHub repository is `CamusFSY/workflow-data-investigator`;
publication remains pending. These notices describe the included scope and do
not independently establish authorship or authorize publication. The maintainer
must confirm the right to license the included original contributions before a
public release.
