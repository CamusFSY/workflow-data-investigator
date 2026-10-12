# Synthetic simulation pass rate

All records were invented for this public integration example. They are not model evaluation results.
The entity is one simulation run, uniquely identified by run_id. The numerator is
outcome = passed; the denominator includes passed and failed runs. Cancelled runs
are excluded. Empty outcomes are excluded and should be reported if present.
period_key is an explicitly assigned experimental window (before or after), not
a timestamp; timezone and calendar boundaries are not used. Compare before as
the baseline with after as the current window. This document supplies the metric
for this synthetic example only; it grants no authority over another dataset.
A descriptive rate change is not a causal effect of the variant or any treatment.
