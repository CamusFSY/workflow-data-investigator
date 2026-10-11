"""Bounded structural evidence and fixed public reasons; no raw response text or headers."""
import json
import re

MAX_CALLS_PER_TURN = 4
KNOWN_TOOLS = {"read_context", "inspect_schema", "query", "analyze", "plot", "finish"}
REASONS = {
    "response_not_object": ("response", "Expected a decoded response object"),
    "choices_invalid": ("choices", "Expected a nonempty choices array"),
    "choice_invalid": ("choices[0]", "Expected a choice object"),
    "message_invalid": ("message", "Expected an assistant message object"),
    "tool_calls_invalid": ("tool_calls", "Expected 1..4 tool calls per turn"),
    "terminal_batch_invalid": ("tool_calls", "finish must be the only call in its turn"),
    "finalization_tool_required": ("tool_calls", "Finalization window requires one finish call; no calls in this batch executed"),
    "call_invalid": ("tool_calls[0]", "Expected a tool call object"),
    "function_invalid": ("tool_calls[0].function", "Expected a function object"),
    "call_type_invalid": ("tool_calls[0].type", "Expected a function tool call"),
    "call_id_invalid": ("tool_calls[0].id", "Expected a tool call ID of 1..128 characters"),
    "function_name_invalid": ("tool_calls[0].function.name", "Expected a string function name"),
    "tool_unknown": ("tool_calls[0].function.name", "Expected a registered tool name"),
    "arguments_invalid": ("tool_calls[0].function.arguments", "Expected JSON text <=12 KiB"),
    "arguments_json_invalid": ("tool_calls[0].function.arguments", "Tool arguments are invalid JSON"),
    "arguments_schema_invalid": ("tool_calls[0].function.arguments", "Arguments do not match the tool schema"),
    "content_invalid": ("content", "Expected null or a UTF-8 encodable public string"),
    "call_id_reused": ("tool_calls[0].id", "Provider reused a tool_call_id"),
    "upstream_validation_rejected": ("upstream", "Parent transport rejected the decoded response"),
}
MISSING = object()
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}\Z")
TOKEN_FIELDS = {"prompt_tokens", "completion_tokens", "total_tokens",
                "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"}


def response_metadata(response):
    """Small allowlist of returned identity/counts; not a billing or authenticity check."""
    result = {}
    if not isinstance(response, dict):
        return result
    model = response.get("model")
    if isinstance(model, str) and MODEL_ID.fullmatch(model):
        result["response_model"] = model
    usage = response.get("usage")
    if isinstance(usage, dict):
        counts = {k: usage[k] for k in sorted(TOKEN_FIELDS) if k in usage
                  and type(usage[k]) is int and 0 <= usage[k] <= 1_000_000_000}
        if counts:
            result["usage"] = counts
            result["usage_source"] = "response_fields_unverified"
    return result


def provider_observation(provider):
    """Filter optional trusted-adapter metadata; never serialize arbitrary provider state."""
    result = {"response_received": False, "dispatch_status": "unknown"}
    try:
        value = getattr(provider, "last_observation", None)
    except Exception:
        return result
    if not isinstance(value, dict):
        return result
    if type(value.get("response_received")) is bool:
        result["response_received"] = value["response_received"]
    if (isinstance(value.get("dispatch_status"), str)
            and value["dispatch_status"] in {"reported_dispatched", "reported_not_dispatched"}):
        result["dispatch_status"] = value["dispatch_status"]
        result["dispatch_source"] = "caller_reported_not_audited"
    model = value.get("requested_model")
    if isinstance(model, str) and MODEL_ID.fullmatch(model):
        result["requested_model"] = model
    reason = value.get("rejection_reason")
    if isinstance(reason, str) and reason in {
            "budget_rejected", "not_authorized", "transport_failed", "recording_exhausted"}:
        result["rejection_reason"] = reason
    result.update(response_metadata({"model": value.get("response_model"),
                                     "usage": value.get("usage")}))
    return result


def shape(value):
    if value is MISSING:
        return {"type": "missing"}
    if value is None:
        return {"type": "null"}
    if isinstance(value, str):
        return {"type": "string", "characters": len(value)}
    if isinstance(value, list):
        return {"type": "array", "items": len(value)}
    if isinstance(value, dict):
        return {"type": "object", "fields": len(value)}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    return {"type": "unsupported"}  # Never use repr() or an arbitrary object's class name.


def enum_shape(value, allowed):
    result = shape(value)
    if isinstance(value, str) and value in allowed:
        result["value"] = value
    return result


def assistant_evidence(message):
    result = shape(message)
    if not isinstance(message, dict):
        return result
    result["role"] = enum_shape(message.get("role", MISSING), {"assistant", "user", "tool", "system"})
    result["content"] = shape(message.get("content", MISSING))
    calls = message.get("tool_calls", MISSING)
    result["tool_calls"] = shape(calls)
    if not isinstance(calls, list):
        return result
    result["tool_calls"]["sample_truncated"] = len(calls) > MAX_CALLS_PER_TURN
    samples = []
    for call in calls[:MAX_CALLS_PER_TURN]:
        sample = shape(call)
        samples.append(sample)
        if not isinstance(call, dict):
            continue
        sample["id"] = shape(call.get("id", MISSING))
        sample["call_type"] = enum_shape(call.get("type", MISSING), {"function"})
        function = call.get("function", MISSING)
        sample["function"] = shape(function)
        if not isinstance(function, dict):
            continue
        sample["function"]["name"] = enum_shape(function.get("name", MISSING), KNOWN_TOOLS)
        arguments = function.get("arguments", MISSING)
        info = shape(arguments)
        sample["function"]["arguments"] = info
        if isinstance(arguments, str) and len(arguments) <= 12000:
            info["utf8_bytes"] = len(arguments.encode("utf-8", errors="replace"))
            if info["utf8_bytes"] <= 12000:
                try:
                    info["json_root"] = shape(json.loads(arguments))
                    info["json_valid"] = True
                except (ValueError, RecursionError) as exc:
                    info["json_valid"] = False
                    if isinstance(exc, json.JSONDecodeError):
                        info["json_error_position"] = {
                            "line": exc.lineno, "column": exc.colno, "offset": exc.pos}
    result["tool_calls"]["sample"] = samples
    # Free text, argument values, unknown fields, reasoning, request and headers are omitted.
    return result


def response_evidence(response):
    """Accept only the decoded response body, never an HTTP request/client or exception."""
    result = shape(response)
    if not isinstance(response, dict):
        return result
    choices = response.get("choices", MISSING)
    result["choices"] = shape(choices)
    if isinstance(choices, list) and choices:
        choice = choices[0]
        result["first_choice"] = shape(choice)
        if isinstance(choice, dict):
            result["first_choice"]["finish_reason"] = enum_shape(
                choice.get("finish_reason", MISSING),
                {"stop", "length", "tool_calls", "function_call", "content_filter",
                 "insufficient_system_resource", "aborted"},
            )
            result["first_choice"]["message"] = assistant_evidence(choice.get("message", MISSING))
    return result


class InvalidResponse(ValueError):
    def __init__(self, code, *, response=MISSING, call_index=None):
        if code not in REASONS:
            code = "upstream_validation_rejected"
        field, message = REASONS[code]
        self.call_index = (call_index if type(call_index) is int
                           and 0 <= call_index < MAX_CALLS_PER_TURN else None)
        if self.call_index is not None:
            field = field.replace("[0]", f"[{self.call_index}]")
        self.reason = {"code": code, "field": field}
        self.response_evidence = None if response is MISSING else response_evidence(response)
        super().__init__(message)


def extract_message(response):
    if not isinstance(response, dict):
        raise InvalidResponse("response_not_object", response=response)
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise InvalidResponse("choices_invalid", response=response)
    if not isinstance(choices[0], dict):
        raise InvalidResponse("choice_invalid", response=response)
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise InvalidResponse("message_invalid", response=response)
    return message
