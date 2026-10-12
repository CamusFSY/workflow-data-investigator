# Methods and theory

Workflow Data Investigator separates one primary answer from supporting evidence. Before execution, the caller fixes the expected columns, value types, nullability, and row-count bounds. An answer-bearing finish is accepted only after reference, role, shape, status, and retained-blocker checks. Supporting evidence stays inspectable without being mistaken for the main answer.

The agent loop is: inspect context and schema, run queries, select a primary result and supporting records, then submit a finish. A normal-phase rejection returns structured feedback and can lead to repair within the original budget. A terminal finish-only rejection ends the run. This describes implemented control flow; it does not promise successful repair.

## What the mathematics establishes

- Conditional structural soundness: with a fixed contract, stable trusted records, and a sound gate, an accepted answer-bearing finish has a successful, complete, contract-conforming primary.
- Shape and meaning are separate: a deterministic shape-only validator cannot distinguish two structurally equivalent results whose numerical correctness differs. A correct table can also have a false summary.
- Bounded repair: finite original request/action caps bound continued attempts. They do not guarantee acceptance or a correct answer.

These are elementary interface properties under explicit assumptions, not novel algorithms or a formal verification of the software.

## What the recorded results show

Three prospective families, one trial per mode, evaluated on the same code build:

- Strict end-to-end success: explicit roles/contract 3/3; legacy 2/3
- Correct substantive answers: both modes 3/3
- Requests: 14 versus 11
- Recorded model-use cost: CNY 0.102346 versus CNY 0.079332

The difference is one repaired shape violation. Separately, an exposed regression produced a correct 19-row ranking but said six singleton colours when its table contains seven. Across all 13 declared trials, all 29 distinct captured SQL results replayed correctly. Diagnostic and exposed panels are not added to the prospective comparison denominator.

The evidence does not establish statistical superiority, improved arithmetic accuracy, lower cost, general reliability, or an official BIRD score. The paper is a research draft in NeurIPS preprint style, not a submitted or accepted conference paper.

## Suggested asset use

- `figures/interface-verification.svg`: method and verification boundaries
- `figures/prospective-results.svg`: paired strict outcomes and resource totals
- `figures/ranking-grounding-failure.svg`: correct table versus contradicted summary

Source code: https://github.com/CamusFSY/workflow-data-investigator
Evaluated commit: a18a07061ea7b9a3e1950b4527e36e266d17b487
