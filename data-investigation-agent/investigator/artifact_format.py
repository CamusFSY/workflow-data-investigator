"""Shared artifact wire format and unchanged reader/writer resource ceilings."""
import json

MAX_MANIFEST_BYTES = 128 * 1024
MAX_ARTIFACT_BYTES = 8 * 1024**2


def json_text(value):
    # Indentation can amplify a valid, compact 64 KiB catalog into many MiB.
    # Preserve every value without whitespace growth proportional to nesting depth.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def write_artifact(path, text, *, limit=MAX_ARTIFACT_BYTES):
    data = text.encode("utf-8")
    if len(data) > limit:
        raise ValueError(f"Artifact {path.name} exceeds its {limit} byte replay limit")
    path.write_bytes(data)
