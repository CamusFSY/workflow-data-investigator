# What the checks establish

The default demonstrations and regression tests use synthetic data and scripted
providers. They establish that tools execute, errors are observable, resource
boundaries are enforced for tested cases and exported actions can be replayed.
They do not establish model autonomy, general correctness, novelty or adoption.

## Repeat the development checks

```sh
cd data-investigation-agent
python3 -B -m unittest discover -s tests -v
python3 -m investigator run \
  --fixture fixtures/join_multiplier \
  --out runs/error-demo --inject-schema-error
python3 runs/error-demo/replay.py
python3 -m investigator run \
  --fixture fixtures/delivery_slip --out runs/group-demo
python3 runs/group-demo/replay.py
python3 -m investigator run \
  --fixture fixtures/missing_definition --out runs/question-demo
python3 runs/question-demo/replay.py
```

The join example preserves a real missing-column error, schema inspection and a
changed subsequent query. Its joined-row and order-level rates differ. The delay
example retains the decline and identifies a group with a larger change. The
missing-definition example returns concrete questions without inventing a rate.
Different traces on these fixtures demonstrate feedback plumbing, not a held-out
model generalization result.

For packaging, use the clean-wheel smoke in [CONTRIBUTING.md](../CONTRIBUTING.md).
It imports the installed package outside the checkout, runs all three delivery
cases and the custom recorded-response example, and checks the documented provider
examples with offline doubles. [Expected demo results](demo-output.md) show the
arithmetic and output statuses to inspect.
For a historical run, prefer its own bundled `replay.py`; installed-runtime replay
is version-sensitive. Successful replay checks consistency against the saved
inputs/results, not source authority or the truth of the final explanation.

## Live evaluation and remaining limits

The optional [answer contract](../data-investigation-agent/docs/evidence-roles.md)
is checked separately from numerical correctness. Fresh synthetic tests include
a correct selected query with several supports, invalid or missing answer IDs,
wrong columns/types/row counts, and a wrong numeric answer with a valid shape.
The latter passes the interface and fails a separate CSV-derived test oracle.
No measured benchmark answer is used to tune these tests. The offline CLI and
configured-client double check exports and replay, not live model improvement.

The [frozen live evaluation](../data-investigation-agent/docs/live-evaluation.md)
reports 13 declared trials at a pinned runtime revision. It separates three
prospective families from diagnostic and previously exposed cases, and retains
both a feedback-driven shape correction and a contradicted prose claim. Its
AI-assisted review and limited public reproducibility are described there.

When recording further evidence, retain successful and unsuccessful attempts
and keep old outputs unchanged. A newly generated scripted report must not be
presented as a previous model-driven result.

A broader model evaluation would need a declared task population, independent data,
fixed budgets, treatment of failures and explicit authority/metric definitions.
It should report all assigned cases and separate intent adoption, numerical
validity and explanation support. The offline tests and demos make no paid model
request. AI-assisted code review is not independent human annotation.
