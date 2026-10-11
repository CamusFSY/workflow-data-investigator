"""Bounded local response files for transparent offline integration examples."""
import copy
import json
from pathlib import Path

from .bundle import safe_read
from .providers import ChatCompletionsProvider, TransportFailure, TransportResponse


class RecordedTransport:
    """Return explicitly supplied response bodies in order; never choose or infer a tool."""
    def __init__(self, path):
        path = Path(path).absolute()
        if any(p.is_symlink() for p in [path.parent, *path.parent.parents]):
            raise ValueError("Symlink recording paths are not accepted")
        data = json.loads(safe_read(path.parent, path.name, 512 * 1024))
        if (not isinstance(data, dict) or type(data.get("format_version")) is not int
                or data["format_version"] != 1
                or not isinstance(data.get("origin"), str)
                or data["origin"] not in {"hand-authored", "user-supplied"}
                or not isinstance(data.get("responses"), list)
                or not 1 <= len(data["responses"]) <= 40):
            raise ValueError("Recording needs format_version 1, origin hand-authored/user-supplied and 1..40 responses")
        self.origin = data["origin"]
        self.responses = data["responses"]
        self.index = 0

    def __call__(self, request, *, timeout_seconds):
        if self.index >= len(self.responses):
            raise TransportFailure("recording_exhausted", dispatched=False)
        response = copy.deepcopy(self.responses[self.index])
        self.index += 1
        return TransportResponse(response, dispatched=False)


class RecordedProvider(ChatCompletionsProvider):
    mode = "offline-recorded"
    label = "OFFLINE RECORDED RESPONSE EXAMPLE; no autonomous model decisions"

    def __init__(self, path):
        # This fixed transport only reads a bounded local JSON file. No client or
        # arbitrary callback can be supplied through this offline entry point.
        super().__init__(RecordedTransport(path), model="offline-recording", allow_data_sharing=True)
