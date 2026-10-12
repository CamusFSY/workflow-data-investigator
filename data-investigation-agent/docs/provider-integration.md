# Provider integration

The public API accepts your own trusted callback or configured client. Its complete
contract and executable examples are below. Nothing imports an SDK, reads keys or
sends data by default. The CLI's `run` is scripted and `investigate` is an offline
response example. A real provider is an explicit Python integration.

## Complete provider contract

A provider must expose all three members before `run` is called:

```python
mode = "live"             # or "mock-scripted" / "offline-recorded"
label = "My provider"     # printable UTF-8 string, 1..200 characters
# Required callable: next(messages, tools, timeout_seconds) -> assistant_message
```

`next` must be callable. The runner validates and snapshots these members before
reading a bundle, creating an output directory or executing any tool. An invalid
contract raises `ValueError`. Once a valid run starts, provider/protocol failures
produce a failed report with its partial trace, diagnostics and offline replay.
Do not use `live` for an offline example or claim that a successful tool replay
establishes model autonomy.

The runner sends the complete current message sequence and currently offered
tool schemas on every turn. Return a Chat Completions assistant message with
one to four tool calls; each has a unique `id`, `type="function"`, a registered
function `name` and JSON-string `arguments`. `finish` must be alone. Preserve
assistant/tool call IDs and the finalization-only schema when it is offered.

The runtime validates a whole batch before executing it, executes in order, and
returns `role="tool"` feedback with the matching `tool_call_id` and `evidence_id`.
SQL errors are actual feedback. Only the next provider turn can use results from
the preceding batch; a response recording does not make new choices from them.

## Working offline example first

From `data-investigation-agent/`, after installing the package in a virtual environment:

```sh
data-investigator validate --bundle examples/simulation_bundle
python examples/recorded_investigation.py \
  --bundle examples/simulation_bundle \
  --responses examples/simulation_responses.json \
  --out runs/simulation-example
python runs/simulation-example/replay.py
```

The same run is available as `data-investigator investigate` with those options.
It uses an unrelated synthetic simulation schema, actual SQLite and fixed
analysis functions. Its nine actions include an invalid column, visible error,
schema inspection, corrected query, rate comparison, chart and cited report.
The JSON responses are **hand-authored**, not outputs from a paid model. The
report says **OFFLINE RECORDED RESPONSES**, with zero live request attempts.
Changing CSV counts changes the computed numbers; the fixed narrative is not a
new diagnosis. These responses are specific to the example's schema and metric.
For a different question or metric, supply a suitable provider and check its
interpretation; passing validation/replay does not approve a business definition.

A recording is a UTF-8 JSON object with `format_version: 1`, `origin` equal to
`hand-authored` or `user-supplied`, and 1..40 Chat Completions response envelopes
in `responses`. It is limited to 512 KiB; linked/non-regular files are rejected.
Exhausted or malformed responses remain visible failures. Recording origin is a
declaration, not proof of which model produced it.

## Your authorized transport or configured client

`ChatCompletionsProvider` adapts
`transport(request, *, timeout_seconds) -> decoded_response`. The callback
receives `model`, `messages`, `tools`, `tool_choice`, `temperature`, `max_tokens`
and `stream`. It must preserve these fields and configure its external timeout.
SDK responses exposing `model_dump()` are accepted too.

```python
from investigator.loop import run
from investigator.providers import ChatCompletionsProvider

def investigate(transport, *, model, bundle, output, goal,
                allow_data_sharing=False, answer_contract=None):
    provider = ChatCompletionsProvider(
        transport, model=model, allow_data_sharing=allow_data_sharing,
        max_output_tokens=2048,
    )
    return run(goal, bundle, output, provider,
               max_steps=12, max_tool_actions=24, max_seconds=60,
               answer_contract=answer_contract)
```

This exact adapter contract is tested offline. `allow_data_sharing=True` must be
an explicit caller decision; without it the adapter fails before transport use.
The [configured-client example](../examples/configured_client.py) accepts an
already configured `client.chat.completions.create(...)` interface and passes
the remaining timeout to it. Importing the example does nothing. Its installed-
wheel contract is tested with an SDK double. A separate [live evaluation](live-evaluation.md)
covers one `deepseek-flash` configuration; it does not certify every SDK/client
path or backend. The caller supplies the SDK/client configuration and credentials
locally; they are not toolkit arguments or exported evidence.

All three Python entry points above, including the legacy budget-reference callback
example, accept an optional `answer_contract`. Supply a caller-owned dictionary
or load an explicitly selected file with
`investigator.evidence.load_answer_contract(path)`. The runner freezes it before
any provider request. See [answer evidence and shape](evidence-roles.md) for the
schema, recorded CLI example and compatibility limits. No model-visible document
can enable or replace this option. Shape validation does not assess numerical
correctness, support relevance or free-text claims.

Before opting in, review the goal, catalog and metric/query/request documents,
schema, SQL text, returned rows, analysis and prior conversation: these can be
sent to your configured endpoint as the model requests tools. Raw CSV files are
not directly attached, but SQL results can disclose their contents over multiple
turns. There is no redaction/anonymization or endpoint-domain allowlist. Use
synthetic inputs or an explicitly reviewed [public snapshot](public-data.md).
The public snapshot registry is currently empty. Inspect the recipient endpoint and its data policy
in the client you configure; the toolkit cannot inspect a trusted callback's
hidden behavior. No data is automatically sent during validation or offline use.

The callback/client owns authorization, credentials, retries, timeouts and
spending policy. Disable SDK retries if you need one client invocation per
provider attempt. The runner limits provider turns (1..40), tool actions (1..40),
provider/tool-loop wall time (1..120 seconds) and context size (250,000 bytes);
input preparation and artifact export are outside that loop deadline. It reserves a finish
opportunity. The adapter sets an output-token request limit (1..8192). These are
**not monetary guarantees**: remote billing, hidden retries, tokenization and
requests already in flight are outside the runner's accounting. No new spend
ledger or budget reset is created.

## Attempts, transport receipts and returned metadata

`provider_requests` counts attempts, including local failures.
`live_request_attempts` counts those in `live` mode. Historical `live_calls` is
retained as an attempts alias; the report UI already labels it “Live 请求尝试”.
It is not a confirmed network-call or billed-request count.

`provider_observations` and `provider_activity` distinguish callback returns,
caller-reported dispatch/non-dispatch and unknown dispatch. Ordinary returned
bodies have **unknown dispatch**; a body can come from a local stub or cache.
`responses_received` counts callback returns, including malformed bodies; it
does not mean the response passed protocol validation.
A trusted transport may use `TransportResponse(response, dispatched=True/False)`
or raise `TransportFailure("budget_rejected", dispatched=False)` to report what
it knows. These receipts are explicitly caller-reported, not independently audited.
Unknown transport failures retain unknown status instead of implying zero cost.

When supplied, the adapter retains bounded requested/returned model identifiers
and allowlisted integer usage fields. These are unverified response metadata,
not a computed charge. Auth headers, request/client objects, exceptions' raw
messages, private reasoning fields and arbitrary usage fields are not exported.
The goal, public action notes, tool inputs and actual tool outputs are evidence;
do not put credentials in any of those public fields.

Existing integrations may keep `DeepSeekProvider(transport, model=...,
parent_budget_reference=...)`. It preserves the legacy callback's
`budget_reference` keyword. This optional identifier refers to the caller's own
accounting. New users should start with the neutral adapter above; its public
signature has no budget-reference parameter.

## Explicit DeepSeek non-thinking smoke

The generic adapter defaults to `thinking=None` and sends no vendor-specific
thinking options. For a DeepSeek smoke, explicitly use `thinking="disabled"`:

```python
provider = ChatCompletionsProvider(
    authorized_transport, model=caller_selected_model,
    allow_data_sharing=True, max_output_tokens=512, thinking="disabled",
)
```

The callback receives top-level `"thinking": {"type": "disabled"}` in each raw
request. Preserve it alongside messages, tools and the remaining timeout.
`DeepSeekProvider(..., parent_budget_reference=existing_reference,
thinking="disabled", max_output_tokens=512)` preserves the existing accounting
callback's `budget_reference` keyword; this does not create a budget or ledger.

The [configured-client wrapper](../examples/configured_client.py) accepts the
same optional `thinking="disabled"` and maps it to
`extra_body={"thinking": {"type": "disabled"}}` for an already configured SDK
client. It does not change client credentials, retries or the endpoint. Configure
SDK retries explicitly in the owning caller; the wrapper and adapter make one
transport invocation per provider attempt and do not retry exceptions.

The wrapper also accepts `max_output_tokens=1024` and `max_steps=8` as explicit
caller overrides; defaults stay compatible. `max_steps` bounds provider requests,
not a token or money budget. The local context byte ceiling is not a proven
input-token ceiling. A caller that needs a monetary limit must reserve a sound
worst-case request cost before dispatch, settle actual usage serially, and stop
before dispatch if the remaining authorization cannot cover that reservation.
Do not turn a desired run count into a promise that the monetary cap can fund it.

Official [request documentation](https://api-docs.deepseek.com/api/create-chat-completion/)
and [thinking/tool-call guidance](https://api-docs.deepseek.com/guides/thinking_mode/)
were checked on 2026-10-11. Thinking is enabled by default there. Thinking-enabled
tool histories require forwarding private reasoning fields; this loop removes
those fields and therefore **does not support that mode**. Explicit `enabled`
is rejected by this adapter. The disabled request flag is recorded as a request
setting, not proof of server behavior. Private reasoning is not persisted or
displayed. No strict-beta endpoint/schema conversion is introduced; current
schemas contain optional fields and use the regular tool-calling contract.

The request options, feedback IDs, single invocation on exceptions and absence
of private reasoning are tested using offline doubles. Those checks alone do
not verify live API compatibility or costs. The [live evaluation](live-evaluation.md)
reports a bounded configuration and estimated costs, not general compatibility
or audited billing. Further live checks require the caller's configured transport
and cost controls.

## Trusted host and interpretation boundaries

Providers and optional clarification resolvers are trusted host code, not an
arbitrary-code sandbox. The POSIX main-thread alarm is a run deadline, not
isolation against a hostile callback. The transport still needs its own network
timeout. A resolver must supply a real user answer or authoritative source; a
model cannot clear missing authority by deleting a question or claiming approval.

Tool references, validation and arithmetic do not prove free-text conclusions,
causal claims or metric authority. Review the copied inputs and returned rows
before sharing evidence. Live evaluation requires separate explicit operational
authorization; offline tests and the examples here require no model API call.
