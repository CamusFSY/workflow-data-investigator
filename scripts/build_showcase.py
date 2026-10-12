#!/usr/bin/env python3
"""Build an allowlisted static Pages artifact from public source; no model calls."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = (
    "index.html", "styles.css", "app.js", "assets/mark.svg",
    "assets/demo.mp4", "assets/demo-poster.jpg", "assets/demo.vtt",
    "assets/demo-transcript.txt", "assets/capture-provenance.json",
)


def build(destination):
    destination = destination.resolve()
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite an existing output: {destination}")
    for asset in ASSETS:
        source = ROOT / "site" / asset
        if source.is_symlink() or not source.is_file() or not source.stat().st_size:
            raise SystemExit(f"Missing or unsafe static asset: {asset}")
    paper = ROOT / "docs/research/technical-report/workflow-data-investigator-technical-report.pdf"
    if paper.is_symlink() or not paper.is_file():
        raise SystemExit("The reviewed technical report PDF must exist before building.")
    destination.mkdir(parents=True)
    for asset in ASSETS:
        target = destination / asset
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "site" / asset, target)
    (destination / ".nojekyll").touch()
    (destination / "paper").mkdir()
    shutil.copyfile(paper, destination / "paper/report.pdf")
    paper_root = paper.parent
    # Explicit paper assets and redistribution notices; no experiment directories.
    paper_assets = (
        "figures/interface-verification.svg", "figures/prospective-results.svg",
        "figures/ranking-grounding-failure.svg", "data/figure_data.json",
        "TEMPLATE_NOTICE.md", "DATA_NOTICE.md", "FONT_NOTICES.md", "GUST-FONT-LICENSE.txt",
        "font-notices/NIMBUS-ROMAN-NOTICES.txt", "font-notices/GNU-GPL-2.txt",
        "font-notices/COMPUTER-MODERN-NOTICES.txt", "font-notices/SIL-OFL-1.1.txt",
        "font-notices/README-Latin-Modern.txt", "font-notices/MANIFEST-Latin-Modern.txt",
        "font-notices/Latin-Modern-Debian-copyright.txt", "font-notices/DEJAVU-LICENSE.txt",
    )
    for relative in paper_assets:
        source = paper_root / relative
        if source.is_symlink() or not source.is_file():
            raise SystemExit(f"Missing or unsafe paper asset: {relative}")
        target = destination / "paper" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    with tempfile.TemporaryDirectory(prefix="wdi-showcase-") as temporary:
        output = Path(temporary) / "simulation"
        subprocess.run([
            sys.executable, "-B", "-m", "investigator", "investigate",
            "--bundle", "examples/simulation_bundle",
            "--responses", "examples/simulation_role_responses.json",
            "--answer-contract", "examples/simulation_answer_contract.json",
            "--out", str(output),
        ], cwd=ROOT / "data-investigation-agent", check=True, capture_output=True)
        subprocess.run([sys.executable, "-B", str(output / "replay.py")], check=True)
        report = json.loads((output / "report.json").read_text())
        assert report["synthetic"] is True and report["live_request_attempts"] == 0
        assert report["tool_actions"] == 9 and report["answer"]["answer_evidence_id"] == "e006"
        # Only this fresh run over the checked-in original synthetic example is copied.
        # No repository-wide copy, arbitrary --bundle input, or private experiment path.
        public_run = destination / "examples/simulation"
        shutil.copytree(output, public_run, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        with zipfile.ZipFile(destination / "assets/simulation-replay.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(public_run.rglob("*")):
                if source.is_file():
                    archive.write(source, Path("simulation") / source.relative_to(public_run))
    total = sum(path.stat().st_size for path in destination.rglob("*") if path.is_file())
    print(f"Built {destination}: {total:,} bytes. Public static assets + original synthetic run only.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist/showcase")
    build(parser.parse_args().out)
