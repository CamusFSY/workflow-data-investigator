"""Offline replay of the tools actually executed. Never invokes a provider."""
import json
from pathlib import Path

from .bundle import digest, safe_read
from .runtime import Runtime


class Replay:
    def __init__(self, root):
        self.root = Path(root).absolute()
        manifest = json.loads(safe_read(self.root, "manifest.json", 65536))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("input"), dict):
            raise ValueError("Invalid manifest: expected an object with an input object")
        for label, mapping in (("input.files", manifest["input"].get("files")),
                               ("runtime", manifest.get("runtime")),
                               ("artifacts", manifest.get("artifacts"))):
            if not isinstance(mapping, dict) or any(
                not isinstance(name, str) or not isinstance(expected, str)
                for name, expected in mapping.items()
            ):
                raise ValueError(f"Invalid manifest: {label} must map file names to hash strings")
        for name, expected in manifest["input"]["files"].items():
            if digest(safe_read(self.root / "input", name, 16 * 1024**2)) != expected:
                raise ValueError(f"Input hash mismatch: {name}")
        for name, expected in manifest["runtime"].items():
            actual = safe_read(self.root / "_replay" / "investigator", name, 100000)
            if digest(actual) != expected:
                raise ValueError(f"Runtime hash mismatch: {name}")
        for name, expected in manifest["artifacts"].items():
            if name == "investigation.ipynb":
                # Kernel execution/auto-save changes notebook outputs and metadata.
                # Embedded events are checked against the hashed original trace below.
                continue
            if digest(safe_read(self.root, name, 8 * 1024**2)) != expected:
                raise ValueError(f"Artifact hash mismatch: {name}")
        lines = (self.root / "trace.jsonl").read_text().splitlines()
        self.events = {event["evidence_id"]: event for event in map(json.loads, lines)}
        self.runtime = Runtime(self.root / "input")

    def check(self, event):
        if event != self.events.get(event["evidence_id"]):
            raise ValueError("Notebook action differs from the original recorded trace")
        if event["tool"] == "external_clarification":
            if event.get("source") != "trusted_caller":
                raise ValueError("External clarification must identify its trusted caller source")
            actual = self.runtime.apply_clarifications(event["evidence_id"], event["input"])
        else:
            actual = self.runtime.call(event["evidence_id"], event["tool"], event["input"])
        if actual != event["result"]:
            raise AssertionError(f"Replay differs at {event['evidence_id']}: {actual!r}")
        return actual


def verify(root):
    root = Path(root)
    replay = Replay(root)
    count = 0
    clarifications = 0
    for line in (root / "trace.jsonl").read_text().splitlines():
        event = json.loads(line)
        if event["tool"] == "run_error":
            continue
        replay.check(event)
        if event["tool"] == "external_clarification":
            clarifications += 1
        else:
            count += 1
    print(f"OFFLINE REPLAY VERIFIED: {count} tool results, "
          "including recorded SQL errors; 0 API calls.")
    if clarifications:
        print(f"{clarifications} trusted caller clarification events replayed; "
              "source authority is not re-verified.")
    if count == 0:
        print("No tool actions were recorded; this does not establish a completed investigation.")
    return count
