"""Integration entry point for the separately authorized, original accounting environment.

Import and call this only after the parent task approves live validation. This file
does not construct a client, fetch credentials, set a budget, or dispatch on import.
"""
from investigator.loop import run
from investigator.providers import DeepSeekProvider


def investigate_with_existing_parent_transport(
    authorized_transport, existing_budget_reference, model, bundle, output, goal,
):
    """transport(request, timeout_seconds=..., budget_reference=...) -> response dict.

    The parent must reserve/check its EXISTING total budget before dispatch, charge
    every real request (including failed requests), own credentials, enforce network
    timeouts, and decide whether any retry is affordable. This adapter never retries.
    Use a non-thinking Chat Completions model configured by the parent.
    """
    provider = DeepSeekProvider(
        authorized_transport,
        model=model,
        parent_budget_reference=existing_budget_reference,
    )
    return run(goal, bundle, output, provider, max_steps=24, max_tool_actions=24, max_seconds=60)
