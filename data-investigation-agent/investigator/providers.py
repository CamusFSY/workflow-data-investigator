"""Provider interface and DeepSeek Chat Completions protocol adapter.

No HTTP client, environment reads, API key argument, retries, or spend ledger.
The trusted parent transport owns authorization, the one existing budget, and charging.
"""
import json

from .protocol import extract_message, response_evidence


class DeepSeekProvider:
    mode = "live"
    label = "DeepSeek / parent-controlled transport"

    def __init__(self, transport, *, model, parent_budget_reference):
        if not callable(transport) or not model or not parent_budget_reference:
            raise ValueError("Supply an authorized parent transport, model, and existing budget reference")
        self.transport = transport
        self.model = model
        # This identifier is not a new budget or accounting store.
        self.parent_budget_reference = parent_budget_reference
        self.response_evidence = None

    def next(self, messages, tools, timeout_seconds):
        self.response_evidence = None
        request = {
            "model": self.model, "messages": messages, "tools": tools,
            "tool_choice": "auto", "temperature": 0, "max_tokens": 2048, "stream": False,
        }
        response = self.transport(
            request, timeout_seconds=timeout_seconds,
            budget_reference=self.parent_budget_reference,
        )
        if hasattr(response, "model_dump"):
            response = response.model_dump()
        self.response_evidence = response_evidence(response)
        return extract_message(response)


def selection(number, tool, args, note):
    return {"role": "assistant", "content": note, "tool_calls": [{
        "id": f"call_{number}", "type": "function",
        "function": {"name": tool, "arguments": json.dumps(args, ensure_ascii=False)},
    }]}
