"""Explicit callback adapters: no HTTP, key discovery, retry or billing ledger."""
import copy
import json
from dataclasses import dataclass

from .protocol import MODEL_ID, extract_message, response_evidence, response_metadata


def provider_contract(provider):
    """Snapshot the complete public contract before any input/output side effects."""
    try:
        mode, label, next_message = provider.mode, provider.label, provider.next
    except Exception:
        raise ValueError("Provider requires mode, label and callable next(messages, tools, timeout_seconds)") from None
    if not isinstance(mode, str) or mode not in {"mock-scripted", "offline-recorded", "live"}:
        raise ValueError("Provider.mode must be mock-scripted, offline-recorded or live")
    if (not isinstance(label, str) or not 1 <= len(label) <= 200
            or any(ord(c) < 32 for c in label)):
        raise ValueError("Provider.label must be a printable string of 1..200 characters")
    try:
        label.encode("utf-8")
    except UnicodeError:
        raise ValueError("Provider.label must be valid UTF-8") from None
    if not callable(next_message):
        raise ValueError("Provider.next must be callable")
    return mode, label, next_message


@dataclass(frozen=True)
class TransportResponse:
    """Optional caller-reported dispatch receipt, not proof of a network call or bill."""
    response: object
    dispatched: object = None


class TransportFailure(RuntimeError):
    """Safe rejection with optional dispatch status supplied by the transport owner."""
    def __init__(self, reason="transport_failed", *, dispatched=None):
        if reason not in {"budget_rejected", "not_authorized", "transport_failed", "recording_exhausted"}:
            reason = "transport_failed"
        if dispatched is not None and type(dispatched) is not bool:
            raise ValueError("dispatched must be boolean or None")
        self.reason = reason
        self.dispatched = dispatched
        super().__init__(reason)


class ChatCompletionsProvider:
    """Adapt an explicitly authorized transport(request, *, timeout_seconds) callback.

    The callback is trusted host code and owns its client, credentials, retries,
    network timeout and spending policy. This adapter provides no monetary cap.
    """
    mode = "live"
    label = "Chat Completions / caller-supplied transport"

    def __init__(self, transport, *, model, allow_data_sharing=False, max_output_tokens=2048,
                 thinking=None):
        if allow_data_sharing is not True:
            raise ValueError("Explicit allow_data_sharing=True is required; context and tool results may leave this host")
        if not callable(transport):
            raise ValueError("transport must be callable")
        if not isinstance(model, str) or not MODEL_ID.fullmatch(model):
            raise ValueError("model must be a public identifier of 1..128 ASCII characters")
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 8192:
            raise ValueError("max_output_tokens must be 1..8192")
        if thinking not in (None, "disabled"):
            raise ValueError("thinking must be None or disabled; thinking-enabled tool history is unsupported")
        self.thinking = thinking
        self.transport = transport
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.response_evidence = None
        self.last_observation = None

    def _send(self, request, timeout_seconds):
        return self.transport(request, timeout_seconds=timeout_seconds)

    def _dispatch(self, dispatched):
        if type(dispatched) is bool:
            self.last_observation["dispatch_status"] = (
                "reported_dispatched" if dispatched else "reported_not_dispatched")

    def next(self, messages, tools, timeout_seconds):
        self.response_evidence = None
        self.last_observation = {"requested_model": self.model, "response_received": False,
                                 "dispatch_status": "unknown"}
        request = {
            "model": self.model, "messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools),
            "tool_choice": "auto", "temperature": 0,
            "max_tokens": self.max_output_tokens, "stream": False,
        }
        if self.thinking == "disabled":
            request["thinking"] = {"type": "disabled"}
            self.last_observation["thinking_requested"] = "disabled"
        try:
            response = self._send(request, timeout_seconds)
        except TransportFailure as exc:
            self._dispatch(exc.dispatched)
            self.last_observation["rejection_reason"] = exc.reason
            raise
        if isinstance(response, TransportResponse):
            self._dispatch(response.dispatched)
            response = response.response
        self.last_observation["response_received"] = True
        if hasattr(response, "model_dump"):
            response = response.model_dump()
        self.last_observation.update(response_metadata(response))
        self.response_evidence = response_evidence(response)
        return extract_message(response)


class DeepSeekProvider(ChatCompletionsProvider):
    """Backward-compatible callback signature for existing caller-owned accounting."""
    label = "DeepSeek / caller-controlled transport"

    def __init__(self, transport, *, model, parent_budget_reference, thinking=None, max_output_tokens=2048):
        if not callable(transport) or not model or not parent_budget_reference:
            raise ValueError("Supply an authorized parent transport, model, and existing budget reference")
        super().__init__(transport, model=model, allow_data_sharing=True,
                         thinking=thinking, max_output_tokens=max_output_tokens)
        # This identifier is not a new budget or accounting store.
        self.parent_budget_reference = parent_budget_reference

    def _send(self, request, timeout_seconds):
        return self.transport(
            request, timeout_seconds=timeout_seconds,
            budget_reference=self.parent_budget_reference,
        )


def selection(number, tool, args, note):
    return {"role": "assistant", "content": note, "tool_calls": [{
        "id": f"call_{number}", "type": "function",
        "function": {"name": tool, "arguments": json.dumps(args, ensure_ascii=False)},
    }]}
