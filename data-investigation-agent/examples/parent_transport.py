"""Legacy callback signature for applications with existing caller-owned accounting.

New integrations should use ChatCompletionsProvider; no private/original project
environment is required. This compatibility example dispatches nothing on import.
"""
from investigator.loop import run
from investigator.providers import DeepSeekProvider


def investigate_with_existing_parent_transport(
    authorized_transport, existing_budget_reference, model, bundle, output, goal,
    *, answer_contract=None,
):
    """transport(request, timeout_seconds=..., budget_reference=...) -> response dict.

    The caller must reserve/check its existing total budget before dispatch, charge
    every real request (including failed requests), own credentials, enforce network
    timeouts, and decide whether any retry is affordable. This adapter never retries.
    Use a tool-capable Chat Completions model configured by the caller.
    """
    provider = DeepSeekProvider(
        authorized_transport,
        model=model,
        parent_budget_reference=existing_budget_reference,
    )
    return run(goal, bundle, output, provider, max_steps=24, max_tool_actions=24, max_seconds=60,
               answer_contract=answer_contract)
