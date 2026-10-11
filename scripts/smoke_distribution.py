#!/usr/bin/env python3
"""Exercise the installed wheel from an unrelated directory; no API calls."""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def provider_examples(python, executable, command, root):
    """Run the exact public examples against the installed wheel; never a real SDK."""
    examples = ROOT / "data-investigation-agent" / "examples"
    bundle = root / "custom-simulation"
    shutil.copytree(examples / "simulation_bundle", bundle)
    validation = json.loads(command([executable, "validate", "--bundle", str(bundle)]))
    assert validation["status"] == "valid" and validation["provider_calls"] == 0
    output = root / "custom-recorded"
    stdout = command([python, "-I", str(examples / "recorded_investigation.py"),
                       "--bundle", str(bundle), "--responses", str(examples / "simulation_responses.json"),
                       "--out", str(output)])
    assert "OFFLINE RECORDED RESPONSES" in stdout
    report = json.loads((output / "report.json").read_text())
    assert report["mode"] == "offline-recorded" and report["live_request_attempts"] == 0
    assert report["status"] == "answered" and report["tool_actions"] == 9
    replay = command([python, "-I", str(output / "replay.py")])
    assert "9 tool results" in replay

    # Only checked-in developer documentation is executable here. This is a test
    # of the exact public Python example, not a model-written-code capability.
    doc = (ROOT / "data-investigation-agent/docs/provider-integration.md").read_text()
    blocks = [b for b in re.findall(r"```python\n(.*?)```", doc, re.S)
              if "def investigate(transport" in b]
    assert len(blocks) == 1
    script = root / "installed-provider-contract.py"
    script.write_text(
        "from unittest.mock import patch\n"
        "network_guard = patch('socket.socket', side_effect=AssertionError('Network forbidden'))\n"
        "network_guard.start()\n" + blocks[0] + '''
import json, runpy, sys, types
from pathlib import Path
from investigator.recording import RecordedTransport
from investigator.replay import verify
bundle, responses, example, outroot = map(Path, sys.argv[1:])
with patch.object(ChatCompletionsProvider, "mode", "mock-scripted"), \\
     patch.object(ChatCompletionsProvider, "label", "OFFLINE installed example contract"):
    try:
        investigate(RecordedTransport(responses), model="offline-contract", bundle=bundle,
                    output=outroot / "no-consent", goal="Offline contract")
    except ValueError:
        assert not (outroot / "no-consent").exists()
    else:
        raise AssertionError("Explicit sharing consent was not enforced")
    first = investigate(RecordedTransport(responses), model="offline-contract", bundle=bundle,
                        output=outroot / "documented-callback", goal="Offline contract",
                        allow_data_sharing=True)
    transport = RecordedTransport(responses)
    def create(**request):
        timeout = request.pop("timeout")
        assert 0 < timeout <= 60
        received = transport(request, timeout_seconds=timeout)
        return types.SimpleNamespace(model_dump=lambda: received.response)
    client = types.SimpleNamespace(chat=types.SimpleNamespace(
        completions=types.SimpleNamespace(create=create)))
    configured = runpy.run_path(str(example))["investigate_with_client"]
    second = configured(client, model="offline-sdk-contract", bundle=bundle,
                        output=outroot / "configured-client", goal="Offline SDK double",
                        allow_data_sharing=True)
    for result, name in [(first, "documented-callback"), (second, "configured-client")]:
        assert result["status"] == "answered" and result["tool_actions"] == 9
        assert result["live_request_attempts"] == 0
        assert verify(outroot / name) == 9
print("INSTALLED PROVIDER CONTRACTS VERIFIED; offline doubles only; zero API calls")
''')
    contracts = command([python, "-I", str(script), str(bundle),
                         str(examples / "simulation_responses.json"),
                         str(examples / "configured_client.py"), str(root)])
    assert "INSTALLED PROVIDER CONTRACTS VERIFIED" in contracts
    return {"mode": "offline-recorded", "validation": "valid", "tool_actions": 9,
            "replay": replay.strip(), "documented_callback_and_sdk_double": "passed; no live validation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", required=True, help="Python in a clean environment with the wheel installed"
    )
    args = parser.parse_args()
    # Do not resolve the venv symlink: Python needs the venv's executable path.
    python = str(Path(args.python).absolute())
    executable = str(Path(args.python).absolute().parent / "data-investigator")
    summaries = []
    with tempfile.TemporaryDirectory(prefix="investigator-wheel-") as temp:
        root = Path(temp)

        def command(argv):
            result = subprocess.run(argv, cwd=root, text=True, capture_output=True, timeout=90)
            if result.returncode:
                raise RuntimeError(
                    f"Command failed ({result.returncode}): {result.stdout}\n{result.stderr}"
                )
            return result.stdout

        command([executable, "--version"])
        # -I prevents importing a checkout or PYTHONPATH accidentally.
        origin = command([
            python, "-I", "-c", "import investigator; print(investigator.__file__)"
        ]).strip()
        assert not Path(origin).is_relative_to(ROOT), "Smoke must exercise an installed wheel"
        for scenario, expected in [("join_multiplier", "answered"), ("delivery_slip", "answered"),
                                   ("missing_definition", "needs_clarification")]:
            bundle = root / f"input-{scenario}"
            shutil.copytree(ROOT / "data-investigation-agent" / "fixtures" / scenario, bundle)
            output = root / f"result-{scenario}"
            invocation = [executable, "run", "--fixture", str(bundle), "--out", str(output)]
            if scenario == "join_multiplier":
                invocation.append("--inject-schema-error")
            stdout = command(invocation)
            assert "SCRIPTED MOCK" in stdout
            report = json.loads((output / "report.json").read_text())
            assert report["status"] == expected, report["status"]
            assert report["live_calls"] == 0
            replay = command([python, "-I", str(output / "replay.py")])
            assert "OFFLINE REPLAY VERIFIED" in replay
            summaries.append({"scenario": scenario, "status": expected, "replay": replay.strip()})
        custom = provider_examples(python, executable, command, root)
    print(json.dumps({"mode": "OFFLINE CONTRACT CHECKS", "model_calls": 0, "installed_module": origin,
                      "scenarios": summaries, "custom_bundle": custom}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
