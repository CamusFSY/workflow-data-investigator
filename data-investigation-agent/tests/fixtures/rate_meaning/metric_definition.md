# Locally authored synthetic rate-meaning probe

These are fictional, pre-aggregated counts for generic tool regressions, not an
approved business metric or an independent author's case. `timely` is a subset of
`completed`; completed and cancelled are disjoint in these fixture counts.

Three checks share this tiny table:

1. `distinct`: completed / total is 8/10 -> 5/10; timely / total is 6/10 -> 3/10.
2. `distinct`: total - completed is 2 -> 5 and includes 1 -> 2 cancellations.
   The arithmetic complement cannot automatically be called late.
3. `equal_ratio`: completed / total is 8/16 -> 12/16, while timely / completed
   is 4/8 -> 9/12. Both ratios are 0.5 -> 0.75, with different numerators,
   denominators and meaning. Numeric equality does not equate the metrics.

Column names and this explanation do not constitute a runtime-validated typed
contract. Generic analytics must remain untyped even when a SQL alias says on_time.
