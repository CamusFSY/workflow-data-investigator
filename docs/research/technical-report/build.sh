#!/usr/bin/env bash
# Compile locally. No model calls, network requests, or publication.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build report.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build report.tex
cp build/report.pdf workflow-data-investigator-technical-report.pdf
