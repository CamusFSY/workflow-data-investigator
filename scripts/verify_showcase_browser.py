#!/usr/bin/env python3
"""Optional local browser QA; requires Playwright, Chromium, and local axe-core JS."""
import argparse
import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_head(self):
        # GitHub Pages serves byte ranges. Python's basic file server does not;
        # implement single-range media reads so seek QA exercises normal hosting.
        path = Path(self.translate_path(self.path))
        range_header = self.headers.get("Range", "")
        if path.suffix == ".mp4" and path.is_file() and range_header.startswith("bytes="):
            bounds = range_header[6:].split("-", 1)
            size = path.stat().st_size
            start = int(bounds[0] or "0")
            end = min(int(bounds[1]) if bounds[1] else size - 1, size - 1)
            if start > end or start >= size:
                self.send_error(416)
                return None
            source = path.open("rb")
            source.seek(start)
            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            self.range_length = end - start + 1
            return source
        return super().send_head()

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "range_length", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        while remaining:
            chunk = source.read(min(65536, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def verify(args):
    from playwright.sync_api import sync_playwright
    directory = args.directory.resolve()
    proof = args.proof.resolve()
    proof.mkdir(parents=True, exist_ok=True)
    # Serve one level up to exercise project Pages URLs under a path prefix.
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(directory.parent)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/{directory.name}/"
    result = {"viewports": [], "errors": [], "axe": {}}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium, args=["--no-sandbox"])
        context = browser.new_context(reduced_motion="reduce", permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        page.on("pageerror", lambda error: result["errors"].append(str(error)))
        page.on("response", lambda response: result["errors"].append(f"HTTP {response.status}: {response.url}") if response.status >= 400 else None)
        for width, height in [(360, 800), (390, 844), (768, 1024), (1440, 1000)]:
            page.set_viewport_size({"width": width, "height": height})
            response = page.goto(url, wait_until="networkidle")
            assert response.status == 200
            assert page.locator("h1").count() == 1
            overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert not overflow, f"Horizontal overflow at width {width}"
            page.evaluate(args.axe.read_text())
            accessibility = page.evaluate("async () => await axe.run(document, {runOnly: {type:'tag', values:['wcag2a','wcag2aa','wcag21aa']}})")
            violations = [{"id": item["id"], "impact": item["impact"], "nodes": [node["target"] for node in item["nodes"]]} for item in accessibility["violations"]]
            result["axe"][str(width)] = violations
            assert not violations, f"Accessibility violations: {violations}"
            # The paper additions must remain usable with native disclosure controls.
            for disclosure in ("#theory", "#paper-results"):
                page.locator(f"{disclosure} summary").click()
                assert page.locator(disclosure).evaluate("element => element.open")
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            expanded = page.evaluate("async () => await axe.run(document, {runOnly: {type:'tag', values:['wcag2a','wcag2aa','wcag21aa']}})")
            assert not expanded["violations"], "Accessibility violation in expanded paper sections"
            if width in (390, 1440):
                page.screenshot(path=str(proof / f"site-{width}-expanded.png"), full_page=True)
            for disclosure in ("#theory", "#paper-results"):
                page.locator(f"{disclosure} summary").click()
            page.evaluate("scrollTo(0, 0)")
            page.screenshot(path=str(proof / f"site-{width}-full.png"), full_page=True)
            page.screenshot(path=str(proof / f"site-{width}-viewport.png"))
            page.locator('nav[aria-label="Main navigation"] a[href="#method"]').click()
            assert page.url.endswith("#method")
            page.locator('nav[aria-label="Main navigation"] a[href="#start"]').click()
            page.locator("#copy-command").click()
            assert page.evaluate("navigator.clipboard.readText()") == page.locator("#quickstart-code").text_content()
            result["viewports"].append({"width": width, "height": height, "overflow": overflow, "navigation": "passed", "clipboard": "passed"})
        page.goto(url, wait_until="networkidle")
        page.locator("#demo-video").scroll_into_view_if_needed()
        media = page.evaluate("""async () => {
          const video = document.querySelector('video');
          video.muted = true;
          await video.play();
          await new Promise(resolve => setTimeout(resolve, 1500));
          const first = video.currentTime;
          const duration = video.duration;
          const seeked = new Promise(resolve => video.addEventListener('seeked', resolve, {once:true}));
          video.currentTime = duration - 2;
          await Promise.race([seeked, new Promise((_,reject)=>setTimeout(()=>reject(Error('Seek timeout')),10000))]);
          const afterSeek = video.currentTime;
          await Promise.race([new Promise(resolve => video.addEventListener('ended', resolve, {once:true})), new Promise(resolve=>setTimeout(resolve,5000))]);
          return {duration, first, ended:video.ended, width:video.videoWidth, height:video.videoHeight,
                  afterSeek, finalTime:video.currentTime, error:video.error, decodedFrames:video.getVideoPlaybackQuality().totalVideoFrames};
        }""")
        (proof / "playback.json").write_text(json.dumps(media, indent=2) + "\n")
        assert 60 <= media["duration"] <= 90 and media["first"] > 0
        assert media["ended"] and media["error"] is None and media["decodedFrames"] > 0
        result["playback"] = media
        page.evaluate("document.querySelector('video').currentTime=48")
        page.wait_for_timeout(500)
        page.screenshot(path=str(proof / "video-playback.png"))
        page.goto(url + "examples/simulation/report.html")
        assert "OFFLINE RECORDED RESPONSES" in page.locator(".banner").inner_text()
        page.locator("#e006 summary").click()
        assert '"passed_runs":3' in page.locator("#e006").inner_text()
        result["actual_report"] = "e004 retained error and e006 selected query inspected"
        page.goto(url)
        page.keyboard.press("Tab")
        assert page.locator(".skip").evaluate("el => el === document.activeElement")
        page.keyboard.press("Enter")
        assert page.url.endswith("#main")
        result["keyboard_skip_link"] = "passed"
        context.close()
        # Verify the core page remains useful without JavaScript.
        no_js = browser.new_context(java_script_enabled=False, viewport={"width":390,"height":844})
        no_js_page = no_js.new_page()
        no_js_page.goto(url)
        assert no_js_page.locator("#quickstart-code").is_visible()
        assert no_js_page.locator("#copy-command").is_hidden()
        assert no_js_page.locator("video source").get_attribute("src") == "assets/demo.mp4"
        result["no_javascript"] = "content, native links, video and quickstart available"
        no_js.close()
        browser.close()
    server.shutdown()
    assert not result["errors"], result["errors"]
    (proof / "browser-checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--axe", type=Path, required=True, help="Installed axe-core/axe.min.js")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    verify(parser.parse_args())
