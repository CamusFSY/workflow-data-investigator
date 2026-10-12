#!/usr/bin/env bash
# Local document rebuild only. No model calls, network access, or publication.
# Standard TeX Live is sufficient; the fallback supports minimal Debian images.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
if ! kpsewhich article.cls >/dev/null 2>&1; then
  export TEXMF="{/usr/share/texlive/texmf-dist,/usr/share/texmf,/var/lib/texmf,/etc/texmf}"
fi
export TEXMFVAR="$PWD/build/texmf-var"
export TEXMFCONFIG="$PWD/build/texmf-config"
export TEXMFCACHE="$PWD/build/texmf-cache"
export XDG_CACHE_HOME="$PWD/build/cache"
mkdir -p "$TEXMFVAR" "$TEXMFCONFIG" "$TEXMFCACHE" "$XDG_CACHE_HOME"
export TEXFORMATS="$PWD/build:"
if ! kpsewhich pdflatex.fmt >/dev/null 2>&1; then
  (cd build && pdftex -ini -etex -interaction=nonstopmode -halt-on-error -jobname=pdflatex pdflatex.ini > format-build.log)
fi
if ! kpsewhich pdftex.map >/dev/null 2>&1; then
  : > build/pdftex.map
  for map in lm.map cm.map symbols.map latxfont.map ps2pk35.map utm.map uhv.map ucr.map; do
    located="$(kpsewhich "$map" || true)"
    if [[ -n "$located" ]]; then cat "$located" >> build/pdftex.map; fi
  done
  export TEXFONTMAPS="$PWD/build:"
fi
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build report.tex > build/build-pass1.log
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build report.tex > build/build-pass2.log
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build report.tex > build/build-pass3.log
cp build/report.pdf workflow-data-investigator-technical-report.pdf
