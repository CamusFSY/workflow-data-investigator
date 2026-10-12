"""Local admission of reviewed public snapshots; no download or model-controlled opt-in.

The registry is trusted source code. It is deliberately empty until an actual
source/license/privacy review pins every model-visible file. Replay checks a
frozen admission record, not current approval or authenticity of an unsigned run.
"""
import copy
import hashlib
import json
import re
from datetime import datetime
from urllib.parse import urlsplit

# Register exact reviewed snapshots here, never in a supplied bundle or tool call.
# Unit tests patch this mapping with explicitly synthetic admission test doubles.
PUBLIC_SNAPSHOTS = {}
HASH = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
PUBLIC_FIELDS = {
    "type", "dataset_id", "snapshot_id", "source_url", "license_id", "license_url",
    "retrieved_at", "upstream_sha256", "transformation", "attribution", "personal_data",
    "sensitive_data", "private_data",
}


def require_synthetic(catalog):
    """Preserve the original synthetic contract, including conflict rejection."""
    if not isinstance(catalog, dict):
        raise ValueError("Catalog must be an object")
    if "synthetic" in catalog and catalog["synthetic"] is not True:
        raise ValueError("catalog.synthetic, when present, must be boolean true")
    provenance = catalog.get("provenance", {})
    if not isinstance(provenance, dict):
        raise ValueError("catalog.provenance must be an object")
    if "type" in provenance and provenance["type"] != "synthetic":
        raise ValueError("Provenance conflicts with a synthetic-only bundle")
    for key in ("real_enterprise_data", "personal_data"):
        if key in provenance and provenance[key] is not False:
            raise ValueError(f"provenance.{key}, when present, must be boolean false")
    explicit = (provenance.get("type") == "synthetic"
                and provenance.get("real_enterprise_data") is False
                and provenance.get("personal_data") is False)
    if catalog.get("synthetic") is not True and not explicit:
        raise ValueError("MVP requires synthetic: true or explicit synthetic provenance "
                         "with real_enterprise_data: false and personal_data: false")


def public_declaration(catalog):
    declaration = catalog.get("provenance")
    if catalog.get("synthetic") is not False:
        raise ValueError("Public real data requires explicit synthetic: false")
    if not isinstance(declaration, dict) or set(declaration) != PUBLIC_FIELDS:
        raise ValueError("Public provenance requires the complete documented source/license/snapshot fields")
    if declaration["type"] != "public-real":
        raise ValueError("Unsupported public provenance type")
    for name in ("dataset_id", "snapshot_id", "license_id"):
        if not isinstance(declaration[name], str) or not ID.fullmatch(declaration[name]):
            raise ValueError(f"Invalid public provenance {name}")
    for name in ("personal_data", "sensitive_data", "private_data"):
        if declaration[name] is not False:
            raise ValueError(f"Public provenance {name} must be boolean false")
    for name in ("source_url", "license_url"):
        value = declaration[name]
        if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
            raise ValueError(f"Invalid public provenance {name}")
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"Public provenance {name} must be an HTTPS source without credentials")
    stamp = declaration["retrieved_at"]
    try:
        if not isinstance(stamp, str) or not stamp.endswith("Z") or "T" not in stamp:
            raise ValueError()
        datetime.fromisoformat(stamp[:-1] + "+00:00")
    except (ValueError, OverflowError):
        raise ValueError("retrieved_at must be an ISO UTC timestamp ending in Z") from None
    if not isinstance(declaration["upstream_sha256"], str) or not HASH.fullmatch(declaration["upstream_sha256"]):
        raise ValueError("upstream_sha256 must identify the downloaded source bytes")
    transformation = declaration["transformation"]
    if not isinstance(transformation, str) or not 1 <= len(transformation.strip()) <= 2000:
        raise ValueError("Document the snapshot extraction/transformation (or explicitly none)")
    attribution = declaration["attribution"]
    if not isinstance(attribution, str) or not 1 <= len(attribution.strip()) <= 2000:
        raise ValueError("Public provenance requires source attribution")
    return declaration


def source_provenance(catalog, files=None, *, registry=None):
    """Validate declarations, then bind actual files before creating output or a provider call.

    The registry argument is only for trusted tests and frozen replay validation;
    it is not exposed by the CLI, run(), or the model's tool interface.
    """
    if not isinstance(catalog, dict):
        raise ValueError("Catalog must be an object")
    declared = catalog.get("provenance")
    if not isinstance(declared, dict) or declared.get("type") != "public-real":
        require_synthetic(catalog)
        result = {"type": "synthetic", "declaration": copy.deepcopy(catalog.get("provenance", {}))}
    else:
        declared = public_declaration(catalog)
        entries = PUBLIC_SNAPSHOTS if registry is None else registry
        entry = entries.get(declared["snapshot_id"])
        if not isinstance(entry, dict):
            raise ValueError("Public snapshot is not allowlisted; a source/license/privacy review is required")
        if set(entry) != {"provenance", "files", "review_reference"} or entry["provenance"] != declared:
            raise ValueError("Public provenance does not match the reviewed allowlist entry")
        reference = entry["review_reference"]
        if not isinstance(reference, str) or not 1 <= len(reference.strip()) <= 1000:
            raise ValueError("Public snapshot requires a recorded review reference")
        expected = entry["files"]
        if not isinstance(expected, dict) or not 5 <= len(expected) <= 24 or any(
                not isinstance(name, str) or not isinstance(value, str) or not HASH.fullmatch(value)
                for name, value in expected.items()):
            raise ValueError("Public allowlist must pin every context and CSV file by SHA256")
        result = {"type": "public-real", "declaration": copy.deepcopy(declared),
                  "approval": copy.deepcopy(entry)}
        if files is not None:
            actual = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
            if actual != expected:
                raise ValueError("Public snapshot file set or SHA256 differs from the reviewed allowlist")
    if files is not None:
        result["catalog_sha256"] = hashlib.sha256(files["catalog.json"]).hexdigest()
    return result


def verify_frozen_provenance(manifest, files):
    """Check frozen byte/declaration consistency; not a new source/privacy/license approval."""
    catalog = json.loads(files["catalog.json"])
    recorded = manifest.get("provenance")
    if recorded is None:  # Compatibility with historical synthetic artifacts only.
        require_synthetic(catalog)
        if manifest.get("synthetic") is not True:
            raise ValueError("Historical replay requires explicit synthetic provenance")
        return source_provenance(catalog, files)
    if not isinstance(recorded, dict):
        raise ValueError("Invalid frozen provenance")
    if not isinstance(recorded.get("declaration"), dict):
        raise ValueError("Invalid frozen provenance declaration")
    approval = recorded.get("approval", {})
    snapshot_id = recorded.get("declaration", {}).get("snapshot_id")
    actual = source_provenance(catalog, files, registry={snapshot_id: approval})
    if actual != recorded or manifest.get("synthetic") is not (actual["type"] == "synthetic"):
        raise ValueError("Frozen provenance differs from input declaration or files")
    return actual


def data_label(provenance):
    return "PUBLIC REAL DATA" if provenance and provenance.get("type") == "public-real" else "SYNTHETIC DATA"


def provenance_reference(provenance):
    return {"type": provenance["type"], "catalog_sha256": provenance.get("catalog_sha256"),
            "snapshot_id": provenance.get("declaration", {}).get("snapshot_id")}
