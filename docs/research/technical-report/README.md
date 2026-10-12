# Evidence Roles and Answer Contracts in Data Analysis Agents

Author: Yiting Feng. No institutional affiliation is listed.

Research draft dated 12 October 2026, formatted using the official NeurIPS 2026 template in preprint mode. This is not a submitted, peer-reviewed, or accepted NeurIPS paper.

## Contents

- [workflow-data-investigator-technical-report.pdf](workflow-data-investigator-technical-report.pdf): 11-page paper, including references and appendices.
- `report.tex`: editable manuscript.
- `neurips_2026.sty`: unmodified official style file; upstream attribution comments retained.
- `figures/`: three figures in PDF, SVG, and PNG formats.
- `data/figure_data.json`: verified, descriptive trial outcomes and aggregate model-use figures used by the charts.
- `build_figures.py`: chart reproduction from the bundled data.
- `build.sh`: local PDF build, with a fallback for minimal Debian TeX installations.
- `homepage-methods-excerpt.md` and `.json`: compact method, theory, result, and caveat copy for an accompanying homepage.
- `TEMPLATE_NOTICE.md`: official-template provenance and notice preservation.
- `DATA_NOTICE.md`: dataset attribution and reuse boundaries.
- `FONT_NOTICES.md` and `font-notices/`: notices for the embedded PDF/figure fonts.

## Rebuild the document

With a standard TeX Live installation:

    bash build.sh

The pre-generated vector figures are included. Regenerating figures is optional and requires Python 3, matplotlib, and numpy:

    python3 build_figures.py
    bash build.sh

No model calls, paid experiments, browser operations, network requests, or publication occur during either build. The aggregate data reproduce the presented figures and totals, not the original agent trials. This package does not claim to be a complete independently rerunnable evaluation release.

## Evidence boundaries

The primary study contains three prospective question families, one trial per mode and family, at evaluated source commit `a18a07061ea7b9a3e1950b4527e36e266d17b487`. Explicit mode passes strict evaluation on 3/3, legacy on 2/3; both modes answer all three substantive questions correctly. The difference is one structural repair, at additional request cost. Diagnostic, smoke, and exposed regression panels remain separately labeled.

The theoretical propositions are elementary conditional properties of an interface model. They are not a new algorithm, a convergence theorem, formal verification of the code, semantic-truth certification, or a statistical reliability guarantee. The implementation was inspected read-only; no runtime was changed for this revision.

## Publication and provenance

This is the current technical report. The [historical overview](../research-overview.md)
describes separate earlier work and is not pooled into this study.
Preserve the [template notice](TEMPLATE_NOTICE.md), [data attribution](DATA_NOTICE.md)
and [font notices](FONT_NOTICES.md) with the paper and figures. The repository's
software license does not replace these third-party notices.

The package contains no credentials, private authorization records, internal
operational paths, provider request transcripts or private billing records.
The template style source is included; the original formatting archive and its
companion example manuscript and checklist are not.

In a read-only home environment, set `MPLCONFIGDIR` and `XDG_CACHE_HOME` to writable
temporary directories before regenerating figures.
