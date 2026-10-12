# Actual offline software demo

The showcase video is a continuous browser capture of the current public
software: a real CLI process, its unmodified generated report, and a real
standalone replay. **OFFLINE RECORDED RESPONSES** is visible throughout.
The source responses are hand-authored, the data is original synthetic data,
and there are no model API calls. This is a workflow demonstration, not a new
autonomous-model evaluation.

[Captioned MP4](../site/assets/demo.mp4) ·
[Poster](../site/assets/demo-poster.jpg) ·
[English WebVTT](../site/assets/demo.vtt) ·
[Accessible text transcript and actual stdout](../site/assets/demo-transcript.txt) ·
[Capture provenance](../site/assets/capture-provenance.json)

The silent, approximately 80-second capture shows:

1. A real `investigate` run over the public simulation example, with the
   explicitly selected caller-owned answer contract.
2. A retained SQL error at `e004`, schema inspection at `e005`, and the corrected
   query at `e006`: two rows with `period_key`, `passed_runs`, `eligible_runs`.
3. The actual report, selected answer and separate supporting sources, followed
   by the generated chart. The measured rates are 5/6 and 3/6, not model scores.
4. A separate replay process verifying all nine results, including the error,
   and retaining the same role/type/shape checks. Free prose is not scored.

## Reproduce the run

From `data-investigation-agent/`, use a new output directory:

```sh
python -B -m investigator investigate \
  --bundle examples/simulation_bundle \
  --responses examples/simulation_role_responses.json \
  --answer-contract examples/simulation_answer_contract.json \
  --out ../runs/my-demo
python -B ../runs/my-demo/replay.py
```

Open `runs/my-demo/report.html`. This requires only the Python standard library.
No keys, private records, experimental packets or paid requests are needed.
Changing inputs can change arithmetic; the fixed choices and narrative do not
become a new model diagnosis.

## Reproduce the capture

Capture-only dependencies are separate from the application's runtime:
Python Playwright, Chromium, FFmpeg with `libx264`, and `ffprobe`. The original
cloud capture used installed tools; versions and source-file hashes are in
`capture-provenance.json`. Install Playwright in a separate capture environment
if needed (`python -m pip install playwright`); provision its browser
dependencies according to that environment's normal package policy. No tool
installation is performed by the script.

From the repository root:

```sh
python scripts/capture_showcase.py \
  --session runs/my-capture \
  --chromium /usr/bin/chromium
```

The script refuses to reuse a session directory. It executes the two real
commands, streams their actual stdout into a readable terminal view, and
navigates the actual report in an iframe. It adds an outer disclosure, chapter
title and English captions without modifying the report or its values.
Reading pauses and navigation are scripted; outputs and results are not.
There is no fake typing, fabricated execution, stock footage, voiceover or music.
The capture is silent to keep file size and dependencies small.

Playwright controls the browser; Chromium's native DevTools screencast records
actual frames, and the script retains their arrival timing. Unchanged frames
remain on screen for their actual duration. System FFmpeg encodes H.264 4:2:0 with fast-start MP4
metadata. English captions are visible in the captured frame and also supplied
as WebVTT. The poster is extracted from an actual video frame. The full source
video, command stdout, cue timing and proof screenshots stay under ignored
`runs/my-capture/`. The script replaces only the six generated media/provenance
assets under `site/assets/`; review those changes before committing them.

The Playwright-specific recorder was absent and its official download was denied
by the cloud network policy. The capture uses the installed Chromium screencast
and system FFmpeg instead; it does not require or retry that download.

The original capture is a cloud Linux recording at 1440 × 900. It does not test
macOS, Windows, Safari or Firefox. Chromium playback and FFmpeg decoding can
verify this artifact without making claims about every browser or device.

## Build the GitHub Pages candidate

```sh
python scripts/build_showcase.py --out dist/showcase
python scripts/check_showcase.py dist/showcase
python -m http.server 8080 --bind 127.0.0.1 --directory dist/showcase
```

Open `http://127.0.0.1:8080/` in that environment. The static builder makes a
fresh run of the same public synthetic example and verifies replay before
including it. The showcased report's values match the video; incidental run
timestamps can differ. A ZIP contains that fresh synthetic run and its frozen
runtime. The output directory must be new.

Only explicit static and paper asset lists (PDF, figures, aggregate figure data
and distribution notices) and the newly generated synthetic run enter the
artifact. The complete repository is
never copied. No live evaluation database or raw live traces are published.
Paper integration uses the existing
`docs/research/technical-report/workflow-data-investigator-technical-report.pdf`
path. The integrated NeurIPS-style revision remains labeled a research draft;
there is one current paper location and no duplicate manuscript.

The [Pages publication proposal](github-pages-proposal.md) defines the exact
repository setting and branch publication steps awaiting review. It adds no
custom Pages workflow or OIDC/write permissions.

## Check accessibility, layout and playback

The optional browser verifier uses an installed local copy of `axe-core`
(`4.10.3` for this candidate) and Playwright. It serves the build beneath a path
prefix, checks 360/390/768/1440-pixel viewports, runs WCAG A/AA checks, exercises
navigation, clipboard and the keyboard skip link, verifies no-JavaScript content,
and plays/seeks the actual MP4 to completion. It saves screenshots and JSON
evidence outside the publication artifact.

```sh
python scripts/verify_showcase_browser.py dist/showcase \
  --axe /path/to/axe-core/axe.min.js \
  --proof artifacts/showcase-review
ffprobe -v error -show_streams -show_format site/assets/demo.mp4
ffmpeg -v error -i site/assets/demo.mp4 -f null -
```

Automated accessibility checks do not cover every assistive technology. Review
the saved desktop/mobile screenshots and video readability as well. The existing
generated report is shown unchanged; the showcase's accessibility checks do not
certify every aspect of that separate report UI.
