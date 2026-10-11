#!/usr/bin/env python3
"""Exercise the installed wheel from an unrelated directory; no API calls."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    print(json.dumps({"mode": "SCRIPTED MOCK", "model_calls": 0, "installed_module": origin,
                      "scenarios": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
