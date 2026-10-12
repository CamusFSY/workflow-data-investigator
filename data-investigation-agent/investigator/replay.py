"""Offline replay of the tools actually executed. Never invokes a provider."""
import json
from pathlib import Path

from .bundle import digest, safe_read
from .artifact_format import MAX_MANIFEST_BYTES, MAX_ARTIFACT_BYTES
from .runtime import Runtime
from .provenance import verify_frozen_provenance, data_label
from .evidence import freeze_answer_contract, contract_digest


class Replay:
    def __init__(self, root):
        self.root = Path(root).absolute()
        # A valid 64 KiB catalog can also carry synthetic provenance metadata;
        # leave bounded room for that metadata plus input/runtime/artifact hashes.
        manifest = json.loads(safe_read(self.root, "manifest.json", MAX_MANIFEST_BYTES))
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
            if digest(safe_read(self.root, name, MAX_ARTIFACT_BYTES)) != expected:
                raise ValueError(f"Artifact hash mismatch: {name}")
        lines = (self.root / "trace.jsonl").read_text().splitlines()
        self.events = {event["evidence_id"]: event for event in map(json.loads, lines)}
        source_files = {name: safe_read(self.root / "input", name)
                        for name in manifest["input"]["files"] if name != "data.sqlite"}
        self.provenance = verify_frozen_provenance(manifest["input"], source_files)
        contract = None
        reference = manifest.get("answer_contract")
        report = json.loads(safe_read(self.root, "report.json", MAX_ARTIFACT_BYTES))
        if not isinstance(report, dict):
            raise ValueError("Invalid report: expected an object")
        if reference is not None:
            if (not isinstance(reference, dict) or set(reference) != {"file", "sha256"}
                    or reference["file"] != "answer_contract.json"
                    or manifest["artifacts"].get(reference["file"]) != reference["sha256"]):
                raise ValueError("Caller answer contract binding is invalid")
            contract = freeze_answer_contract(json.loads(safe_read(self.root, reference["file"], 65536)))
            if (contract is None or report.get("evidence_interface") != "answer_roles_v1"
                    or report.get("answer_contract") != contract
                    or report.get("answer_contract_sha256") != contract_digest(contract)):
                raise ValueError("Report and frozen caller answer contract differ")
        elif ("answer_contract.json" in manifest["artifacts"]
              or any(key in report for key in ("evidence_interface", "answer_contract", "answer_contract_sha256"))):
            raise ValueError("Caller answer contract cannot silently become legacy mode")
        self.runtime = Runtime(self.root / "input", provenance=self.provenance, answer_contract=contract)

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
    print(data_label(replay.provenance) + "; frozen provenance and file hashes checked; "
          "source/license/privacy approval is not re-verified. Free prose is not scored.")
    if replay.runtime.answer_contract is not None:
        answer = replay.runtime.finished or {}
        print("CALLER-FROZEN ANSWER ROLES: " + json.dumps({
            "answer_evidence_id": answer.get("answer_evidence_id"),
            "supporting_evidence_ids": answer.get("supporting_evidence_ids", []),
            "answer_contract_sha256": contract_digest(replay.runtime.answer_contract),
        }, sort_keys=True))
        print("Role/source/type/shape checks replayed; numerical correctness and support relevance are not scored.")
    if clarifications:
        print(f"{clarifications} trusted caller clarification events replayed; "
              "source authority is not re-verified.")
    if count == 0:
        print("No tool actions were recorded; this does not establish a completed investigation.")
    return count
