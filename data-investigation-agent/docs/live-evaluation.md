# Frozen live evaluation

This bounded evaluation observed a model correct an answer-shape error after
tool feedback. It also retained a separate case where the model's prose
contradicted a correct query result. Completion, replay and shape validation
therefore remain distinct from factual correctness.

## Runtime and comparison

All trials used runtime commit
[`a18a07061ea7b9a3e1950b4527e36e266d17b487`](https://github.com/CamusFSY/workflow-data-investigator/commit/a18a07061ea7b9a3e1950b4527e36e266d17b487),
tree `b139cd5bf3638465ecf7b530f3d1ef0119397d9a`.
The model was `deepseek-flash`, temperature `0`, with thinking disabled in the
request configuration. The same runtime supported both comparison arms:
legacy evidence references, and explicit answer/support roles with a frozen
[answer-shape contract](evidence-roles.md).

[Hosted CI for that revision](https://github.com/CamusFSY/workflow-data-investigator/actions/runs/38204252786)
passed 165 tests on each of Python 3.11 and 3.12, plus build and installed-wheel
smoke checks. Those offline checks validate implementation behavior; the live
observations below are separate evidence.

## Results by declared group

All 13 declared trials completed. Groups are reported separately because their
exposure and purpose differ. Overall pass is the group's combined assessment,
not merely completion or replay success.

| Group | Trials | Observed outcome |
| --- | --- | --- |
| Primary prospective families 744, 745 and 800; one sample per arm per family | 6 | Roles: 3/3 overall; legacy: 2/3 overall. Both arms answered all questions, with no unsupported prospective claims. |
| Related sign diagnostic 829 | 2 | Both arms passed; separate from the primary denominator. |
| Previously exposed smoke 764 | 1 | Passed; separate from the prospective comparison. |
| Previously exposed roles regressions 723, 728, 733 and 765 | 4 | Numerical: 4/4; overall: 3/4. |

In legacy trial 745, the selected result contained both `publisher_id` and
`publisher_name` despite a frozen one-column requirement. The numeric prose was
correct, but strict primary-answer verification was **unverifiable** because
the result shape did not comply. The roles arm initially made the same shape
error, received `answer_columns_mismatch`, and corrected it within the same
trial. This observed difference concerns structural compliance; it does not
establish improved arithmetic or reasoning.

In roles regression 728, the correct 19-row query result contained **seven**
singleton colours, while the summary said **six**. That contradicted statement
remains a failure; neither correct SQL nor a completed finish makes the prose
correct.

The aggregate review dimensions below have different meanings and are not a
single pooled success score:

| Dimension | Result | Meaning |
| --- | --- | --- |
| Delivery completion | 13/13 | A final delivery was completed. |
| Selected-primary shape conformance | 12/13 | The selected primary result conformed to the required shape; legacy 745 returned an extra column. |
| Strict primary-answer verification | 12/13 | The primary answer met strict verification; legacy 745 was unverifiable under the required shape. |
| Narrative grounding | 12/13 | The reviewed narrative was supported; regression 728 contained the contradiction above. |
| Question coverage | 13/13 | The requested questions were covered. |

Review identified one contradicted claim among 114 reviewed claim atoms. This
is a descriptive inventory from AI-assisted review, not a statistical guarantee
of factual reliability.

## Execution and review evidence

The 13 trials used 53 model requests, 153,782 input tokens, 8,557 output tokens
and 88 tool actions. Four finish attempts were rejected: three duplicate-support-ID
errors and one answer-column mismatch. All four were recoverable within their
trials and were retained without paid trial reruns.
Each trial had an independent-process replay. An evaluator outside the runner
also replayed 29 distinct captured SQL results against the cleared public-data
projection. Replay verifies the recorded computations against their inputs; it
does not by itself verify every narrative claim.

The review used a compact evidence export, not a reconstruction of every provider
wire request. Independent request-envelope and tool-schema arrays were absent;
equal-setting checks relied on frozen configuration provenance and observed mode
behavior. The original full-export hash was not recomputed. Request wall times
were unavailable, so no latency comparison is reported.

For the three primary prospective families, the observed request and accounting
totals were:

| Arm | Model requests | Conservative usage-based accounting |
| --- | --- | --- |
| Legacy | 11 | CNY 0.079332 |
| Explicit answer/support roles | 14 | CNY 0.102346 |

The roles arm's observed structural improvement therefore came with more
requests and higher accounted usage in this small comparison. These totals
exclude the diagnostic, smoke and exposed regression groups.

Review was AI-assisted, including a fresh mode/status-blinded narrative review.
Blinding was imperfect because the reviewed content could reveal related tasks.
Separately, six grain/key claims relied on background source context.
It was **not independent human review**. Conservative usage-based
accounting was **CNY 0.376020** for the current phase and **CNY 0.567558**
cumulatively for the current evaluation. These are estimates, not a provider
invoice or a price guarantee for future runs.

## Data and attribution

The evaluation used an adapted, cleared five-table superhero projection of the
BIRD Mini-Dev SQLite data: **6,802 total rows**, upstream revision
`f65faf4ae3b638c1fa6df1d3370c8d92c8366301`. This is public data, not synthetic
data and not the complete benchmark.

Attribution: the BIRD team, [BIRD Mini-Dev repository](https://github.com/bird-bench/mini_dev)
and [official dataset card](https://huggingface.co/datasets/birdsql/bird_mini_dev).
The dataset is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
The projection changes the data's scope; the toolkit's code remains
[Apache-2.0](../LICENSE). External data and reference answers are not bundled
with the toolkit.

## Interpretation and reproducibility limits

The schema was known. The primary comparison contains only three scalar
question families, with one sample per arm per family. Public-data exposure,
including possible training exposure, is uncertain; previously exposed cases
are explicitly separated above. These observations establish neither statistical
significance nor generalization, broad model superiority, novelty or adoption.
They are not an official BIRD score, a full benchmark run or evidence of
production readiness.

The earlier **2026-10-11 guidance comparison**, strict **2/4 versus 3/4**, is a
different experiment. Its results remain unchanged and are not pooled with or
reinterpreted through this comparison.

This public summary contains aggregate results and selected failure descriptions.
The evaluation database, reference answers and raw live traces are not included,
so this summary alone cannot independently reproduce the exact live scores.
The pinned source and included offline examples remain available for inspecting
the implementation and replay behavior.

The project remains alpha. This evaluation covers one model configuration,
not every SDK/client path or backend. Thinking-enabled tool histories remain
unsupported. The [provider integration guide](provider-integration.md) describes
those boundaries; the CLI demonstrations remain explicitly offline.
