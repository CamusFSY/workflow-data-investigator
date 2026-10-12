#!/usr/bin/env python3
"""Capture actual offline CLI output and the untouched generated report. No model calls.

Requires Python Playwright, Chromium, FFmpeg (libx264), and ffprobe.
Raw capture/run stay under ignored runs/. Only reviewed video assets are exported.
"""
import argparse
import asyncio
import base64
import functools
import hashlib
import json
import shutil
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = """<!doctype html><html lang="en"><meta charset="utf-8"><title>Actual offline software capture</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#eef1e9;color:#183c35;font:20px/1.5 Arial,sans-serif}
header{height:64px;background:#153f39;color:#f3f5eb;display:flex;align-items:center;justify-content:space-between;padding:0 32px;font-size:18px}
header strong{font-size:15px;letter-spacing:.04em;color:#f1dfa5}h1{font:32px/1.3 Georgia,serif;margin:16px 32px 4px}
.context{margin:0 32px 14px;color:#53675e;font-size:16px}#screen{margin:0 28px;height:660px;border:1px solid #a9b8a9;border-radius:5px;overflow:hidden;background:white}
iframe{border:0;width:100%;height:100%;display:block}#terminal{height:100%;overflow:auto;padding:28px;background:#102e2a;color:#e9f2df;white-space:pre-wrap;overflow-wrap:anywhere;font:18px/1.65 'DejaVu Sans Mono',monospace;margin:0}
footer{position:fixed;bottom:0;height:89px;width:100%;background:#faf8ec;border-top:1px solid #d5ceaa;display:flex;align-items:center;padding:14px 32px;font-size:23px;line-height:1.35;font-weight:500}
</style><header><span>Workflow Data Investigator / Actual software capture</span><strong>OFFLINE RECORDED RESPONSES · 0 MODEL API CALLS</strong></header>
<h1 id="title"></h1><p class="context">Original synthetic CSVs · Hand-authored provider responses · Real SQL execution and replay</p>
<main id="screen"><pre id="terminal"></pre><iframe id="report" title="Actual generated investigation report" hidden></iframe></main>
<footer id="caption"></footer></html>"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{milliseconds:03}"


async def capture(args):
    from playwright.async_api import async_playwright
    session = args.session.resolve()
    session.relative_to(ROOT / "runs")
    if session.exists():
        raise SystemExit("Use a new session path; prior evidence is never overwritten.")
    session.mkdir(parents=True)
    (session / "capture.html").write_text(SHELL)
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    run_dir = session / "run"
    output_relative = "../" + run_dir.relative_to(ROOT).as_posix()
    commands = [
        [sys.executable, "-B", "-m", "investigator", "investigate",
         "--bundle", "examples/simulation_bundle",
         "--responses", "examples/simulation_role_responses.json",
         "--answer-contract", "examples/simulation_answer_contract.json",
         "--out", output_relative],
        [sys.executable, "-B", str(Path(output_relative) / "replay.py")],
    ]
    display_command = (
        "$ python -B -m investigator investigate \\\n"
        "    --bundle examples/simulation_bundle \\\n"
        "    --responses examples/simulation_role_responses.json \\\n"
        "    --answer-contract examples/simulation_answer_contract.json \\\n"
        f"    --out {output_relative}\n\n"
    )
    transcript, cues = [], []
    assets = ROOT / "site/assets"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=args.chromium, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1440, "height": 900},
                                            reduced_motion="reduce")
        page = await context.new_page()
        await page.goto(base + "/" + (session / "capture.html").relative_to(ROOT).as_posix())
        # Native Chromium screencast + installed FFmpeg. No Playwright recorder
        # download, no synthetic frames, and no fabricated terminal animation.
        frame_directory = session / "raw-video"
        frame_directory.mkdir()
        recorded_frames = []
        cdp = await context.new_cdp_session(page)

        async def on_frame(event):
            now = time.monotonic()
            frame_path = frame_directory / f"{len(recorded_frames):06d}.jpg"
            frame_path.write_bytes(base64.b64decode(event["data"]))
            recorded_frames.append((frame_path, now))
            await cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})

        cdp.on("Page.screencastFrame", on_frame)
        started = time.monotonic()
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
                       "maxWidth": 1440, "maxHeight": 900, "everyNthFrame": 1})

        async def stage(title, caption):
            cues.append({"start": time.monotonic() - started, "title": title, "text": caption})
            await page.locator("#title").evaluate("(el, text) => el.textContent = text", title)
            await page.locator("#caption").evaluate("(el, text) => el.textContent = text", caption)

        async def hold(seconds):
            await asyncio.sleep(seconds)

        async def execute(command, label):
            # Read the real process pipe as it arrives. No simulated typing or outputs.
            process = await asyncio.create_subprocess_exec(
                *command, cwd=ROOT / "data-investigation-agent", stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
            output = ""
            while line := await process.stdout.readline():
                text = line.decode("utf-8")
                output += text
                await page.locator("#terminal").evaluate(
                    "(el, text) => { el.append(document.createTextNode(text)); el.scrollTop=el.scrollHeight; }", text)
            code = await process.wait()
            transcript.append({"command": label, "exit_code": code, "stdout": output})
            if code:
                raise RuntimeError(f"Offline command failed with exit {code}")
            return output

        await stage("01 / Run the included example", "Run real tools with a frozen answer contract. The provider responses are hand-authored; no model is called.")
        await page.locator("#report").evaluate("el => el.style.display='none'")
        await page.locator("#terminal").evaluate("(el, text) => el.textContent=text", display_command)
        await hold(6)
        await execute(commands[0], display_command.strip())
        await stage("02 / Keep the actual feedback", "The CLI retains the bad-column error, inspects schema, then executes the fixed correction.")
        await page.locator("#terminal").evaluate("el => el.scrollTop=470")
        await hold(10)

        report = json.loads((run_dir / "report.json").read_text())
        assert report["mode"] == "offline-recorded" and report["synthetic"]
        assert report["tool_actions"] == 9 and report["live_request_attempts"] == 0
        assert report["answer"]["answer_evidence_id"] == "e006"
        await page.locator("#terminal").evaluate("el => el.style.display='none'")
        await page.locator("#report").evaluate("(el, src) => {el.hidden=false;el.style.display='block';el.src=src;}",
                                              base + "/" + (run_dir / "report.html").relative_to(ROOT).as_posix())
        frame = page.frame_locator("#report")
        await frame.locator("h1").wait_for()
        await stage("03 / Open the generated report", "The actual report records nine tool actions, one visible error, and zero live request attempts.")
        await hold(8)
        await page.screenshot(path=str(session / "report-proof.png"))

        async def reveal(evidence_id):
            target = frame.locator("#" + evidence_id)
            if not await target.get_attribute("open") == "":
                await target.locator("summary").click()
            await target.evaluate("el => el.scrollIntoView({block:'start',behavior:'instant'})")

        await reveal("e004")
        await stage("04 / Inspect the retained error", "e004 really failed: ‘no such column: reporting_week’. The rejected query and its return stay visible.")
        await hold(8)
        await reveal("e005")
        await stage("05 / Inspect the schema", "e005 exposes period_key, the available column. This example's next action is fixed, not a fresh model choice.")
        await hold(8)
        await reveal("e006")
        await stage("06 / Inspect the corrected answer query", "e006 uses period_key and excludes cancelled runs. Actual counts: before 5/6; after 3/6.")
        await hold(10)
        await page.screenshot(path=str(session / "answer-proof.png"))
        await stage("07 / Separate answer from supporting evidence", "The report selects e006 as the answer and e002, e003, e007, e008 as support. The caller's contract is retained.")
        await frame.locator(".summary").evaluate("el => el.scrollIntoView({block:'start',behavior:'instant'})")
        await hold(9)
        await stage("08 / Check the arithmetic's scope", "The generated chart shows 83.3% to 50.0%. This descriptive change does not establish cause or validate prose.")
        await frame.locator("figure").evaluate("el => el.scrollIntoView({block:'start',behavior:'instant'})")
        await hold(8)
        await page.locator("#report").evaluate("el => el.style.display='none'")
        await page.locator("#terminal").evaluate("el => {el.style.display='block';el.textContent='';}")
        replay_label = f"$ python -B {output_relative}/replay.py\n\n"
        await page.locator("#terminal").evaluate("(el,text) => el.textContent=text", replay_label)
        await stage("09 / Replay the exported evidence", "Replay verifies all nine recorded tool results, including the SQL error, without API calls. Free prose is not scored.")
        await execute(commands[1], replay_label.strip())
        await page.locator("#terminal").evaluate("el => el.scrollTop=0")
        await hold(12)
        await page.screenshot(path=str(session / "replay-proof.png"))
        duration = time.monotonic() - started
        await cdp.send("Page.stopScreencast")
        await context.close()
        await browser.close()
    server.shutdown()
    (session / "commands.json").write_text(json.dumps(transcript, indent=2, ensure_ascii=False) + "\n")
    (session / "cues.json").write_text(json.dumps(cues, indent=2) + "\n")
    if not recorded_frames:
        raise RuntimeError("Chromium returned no actual screencast frames")
    concat = []
    for index, (frame_path, frame_time) in enumerate(recorded_frames):
        next_time = recorded_frames[index + 1][1] if index + 1 < len(recorded_frames) else started + duration
        concat.extend([f"file '{frame_path.name}'", f"duration {max(next_time - frame_time, 0.001):.6f}"])
    concat.append(f"file '{recorded_frames[-1][0].name}'")
    frame_list = frame_directory / "frames.txt"
    frame_list.write_text("\n".join(concat) + "\n")
    (session / "frame-timing.json").write_text(json.dumps([
        {"file": path.name, "elapsed_seconds": frame_time - started} for path, frame_time in recorded_frames
    ], indent=2) + "\n")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(frame_list),
                    "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-r", "25", "-movflags", "+faststart", str(assets / "demo.mp4")], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "20", "-i", str(assets / "demo.mp4"),
                    "-frames:v", "1", "-q:v", "2", str(assets / "demo-poster.jpg")], check=True)
    vtt, text = ["WEBVTT", ""], ["Workflow Data Investigator — actual offline software capture", "",
        "OFFLINE RECORDED RESPONSES. Original synthetic data. Hand-authored choices.",
        "The CLI, SQL, generated report and replay in this video are actual execution.",
        "Silent capture with captions; reading pauses and report navigation are scripted.", ""]
    for index, cue in enumerate(cues):
        end = cues[index + 1]["start"] if index + 1 < len(cues) else duration
        vtt.extend([f"{timestamp(cue['start'])} --> {timestamp(end)}", cue["text"], ""])
        text.extend([f"{timestamp(cue['start'])}  {cue['title']}", cue["text"], ""])
    text.extend(["ACTUAL COMMAND OUTPUT (not fabricated or summarized)", ""])
    for command in transcript:
        text.extend([command["command"], command["stdout"], f"Exit code: {command['exit_code']}", ""])
    (assets / "demo.vtt").write_text("\n".join(vtt))
    (assets / "demo-transcript.txt").write_text("\n".join(text), encoding="utf-8")
    source_files = [path for path in (ROOT / "data-investigation-agent/investigator").glob("*.py")]
    source_files += list((ROOT / "data-investigation-agent/examples/simulation_bundle").glob("*"))
    source_files += [ROOT / "data-investigation-agent/examples/simulation_role_responses.json",
                     ROOT / "data-investigation-agent/examples/simulation_answer_contract.json"]
    provenance = {
        "disclosure": "OFFLINE RECORDED RESPONSES; actual local tool execution; no model calls",
        "public_source_base": "fd6d35392969ff8f34d7c7de548fc943283e4f3b",
        "capture_method": "Chromium native screencast of actual subprocess stdout and unmodified generated report, controlled with Playwright; actual frame timing; system FFmpeg H.264",
        "runtime_modified": False, "model_api_calls": 0,
        "tool_actions": 9, "retained_sql_error": "e004", "answer_evidence_id": "e006",
        "sha256": {str(path.relative_to(ROOT)): digest(path) for path in sorted(source_files) if path.is_file()},
        "capture_script_sha256": digest(Path(__file__)),
        "mp4_sha256": digest(assets / "demo.mp4"),
        "report_sha256": digest(run_dir / "report.html"),
        "trace_sha256": digest(run_dir / "trace.jsonl"),
        "tools": {"python": sys.version.split()[0], "chromium": subprocess.check_output([args.chromium, "--version"], text=True).strip(),
                  "ffmpeg": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]},
    }
    (assets / "capture-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps({"duration_seconds": duration, "video": str(assets / "demo.mp4"), "session": str(session)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True, help="New directory under runs/")
    parser.add_argument("--chromium", default=shutil.which("chromium") or "chromium")
    asyncio.run(capture(parser.parse_args()))
