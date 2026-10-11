# Provider integration

A provider implements:

```python
next(messages, tools, timeout_seconds) -> assistant_message
```

The runtime sends the complete current message sequence and tool schemas on
every turn. Return a Chat Completions assistant message with one to four tool
calls; each has a unique `id`, `type="function"`, a registered function `name`
and a JSON-string `arguments`. `finish` must be the only call in its batch.

The runtime validates a whole batch before executing it, runs tools in order,
and returns `role="tool"` feedback with the corresponding `tool_call_id` and
`evidence_id`. SQL execution errors are feedback, not fabricated successful
results. Calls in one batch were chosen before any result from that batch was
visible; only the following provider turn can adapt to those results.

The public runner uses positional parameters:

```python
from investigator.loop import run

outcome = run(goal, fixture_directory, output_directory, provider,
              max_steps=24, max_seconds=60, max_tool_actions=24)
```

`ScriptedMock` implements this contract for development only. The existing
`DeepSeekProvider` translates it to a caller-supplied transport:

```python
from investigator.providers import DeepSeekProvider

provider = DeepSeekProvider(
    authorized_transport,
    model=model_identifier,
    parent_budget_reference=existing_budget_reference,
)
```

This is an interface example, not a runnable paid example. The transport is a
trusted callback accepting `(request, *, timeout_seconds, budget_reference)`.
It must enforce authorization, the existing cumulative budget, actual billing
and external timeouts. It must send the supplied messages and tools unchanged,
including the finalization-only schema when provided. The adapter does not
load keys, discover credentials, perform HTTP, retry, or create a spend ledger.

Tool references and schema validation do not establish the truth of a model's
explanation. Report numerical correctness, metric adoption and prose support
separately. Label recorded executions as model-driven only when they actually
used a model, and retain failed attempts. Do not present scripted demo routes as
autonomous behavior.

## Trusted host responsibilities

Providers and optional clarification resolvers run as trusted host code, not in
an arbitrary-code sandbox. The loop uses a POSIX main-thread alarm for its wall
deadline; transports must still configure their own external request timeouts.
This is not isolation against a hostile callback that alters host state. A resolver
must provide a real user answer or authoritative source rather than trusting a
model's claim of approval. Recorded public notes are bounded; private model
reasoning fields are not required or retained.

Review exported data before sharing. The report contains copied inputs and
actual returned rows. Paid integration tests require separate, explicit
operational authorization; the repository's offline tests never need one.
