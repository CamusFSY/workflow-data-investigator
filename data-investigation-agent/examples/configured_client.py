"""Optional explicit live integration; no imports, key lookup or dispatch on import.

The caller supplies an already configured Chat Completions SDK client. Configure
its base URL, credentials, spending controls and retries outside this module.
Disable client retries if you need one client request per provider attempt.
No monetary guarantee or end-to-end live validation is claimed here.
"""
from investigator.loop import run
from investigator.providers import ChatCompletionsProvider


def investigate_with_client(client, *, model, bundle, output, goal,
                            allow_data_sharing=False, max_steps=12,
                            max_tool_actions=24, max_seconds=60):
    def transport(request, *, timeout_seconds):
        return client.chat.completions.create(**request, timeout=timeout_seconds)

    provider = ChatCompletionsProvider(
        transport, model=model, allow_data_sharing=allow_data_sharing,
        max_output_tokens=2048,
    )
    return run(goal, bundle, output, provider, max_steps=max_steps,
               max_tool_actions=max_tool_actions, max_seconds=max_seconds)
