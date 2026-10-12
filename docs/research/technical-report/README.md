# Evidence Roles and Answer Contracts in Data Analysis Agents

A Small Same Build Validation of Workflow Data Investigator

Author: Yiting Feng (GitHub: CamusFSY)

Date: 12 October 2026

Status: Technical report draft. No claim of conference acceptance or peer review.

The report describes the 13-trial October 12 product-interface study. Three fresh question families pass strict end-to-end checks in explicit mode (3/3) versus legacy mode (2/3). Both modes answer the substantive questions correctly; the difference is one output-shape repair. Explicit mode costs CNY 0.102346 across 14 requests versus CNY 0.079332 across 11 requests. A separate ranking regression still contains a prose contradiction despite its correct table.

This is a small combined interface/contract/instruction ablation, not demonstrated arithmetic superiority or an official BIRD score. The separate historical 64-episode clarification pilot is not pooled with the product study. The original twelve-page historical manuscript was not reviewed or replaced. This new report does not depend on access to that old manuscript.

## Files

- `report.tex`: editable LaTeX source
- `workflow-data-investigator-technical-report.pdf`: compiled report, when distributed with this source

## Build

Use a standard LaTeX installation with pdfLaTeX, Latin Modern, microtype, geometry, amsmath, booktabs, enumitem, hyperref, fancyhdr, titlesec, and balance. Build twice to resolve references:

```
pdflatex -interaction=nonstopmode -halt-on-error report.tex
pdflatex -interaction=nonstopmode -halt-on-error report.tex
```

The study's source commit is [a18a070](https://github.com/CamusFSY/workflow-data-investigator/commit/a18a07061ea7b9a3e1950b4527e36e266d17b487). See its [interface documentation](https://github.com/CamusFSY/workflow-data-investigator/blob/a18a07061ea7b9a3e1950b4527e36e266d17b487/data-investigation-agent/docs/evidence-roles.md).

Data attribution: [BIRD Team, BIRD-SQL Mini-Dev](https://huggingface.co/datasets/birdsql/bird_mini_dev), adapted five-table projection, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). This report does not distribute the database or claim that the software license replaces the data license.
