#!/usr/bin/env python3
"""Check a built Pages tree for broken local links and accidental publication."""
import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.ids = set()
        self.feed(source)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("id"):
            if attrs["id"] in self.ids:
                raise ValueError(f"Duplicate element ID: {attrs['id']}")
            self.ids.add(attrs["id"])
        for attribute in ("href", "src", "poster"):
            if attrs.get(attribute):
                self.links.append(attrs[attribute])


def check(directory):
    directory = directory.resolve()
    documents = {path: Document(path.read_text()) for path in directory.rglob("*.html")}
    checked = 0
    errors = []
    for path, document in documents.items():
        for value in document.links:
            url = urlsplit(value)
            if url.scheme or url.netloc:
                prefix = "https://github.com/CamusFSY/workflow-data-investigator/blob/main/"
                if value.startswith(prefix):
                    source = ROOT / unquote(value[len(prefix):].split("#")[0])
                    if not source.is_file():
                        errors.append(f"Missing linked repository source: {value}")
                continue
            if value.startswith("/"):
                errors.append(f"Root-relative link breaks project Pages base path: {value}")
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not target.is_relative_to(directory) or not target.exists():
                errors.append(f"{path.relative_to(directory)} -> missing/outside {value}")
            elif url.fragment and target in documents and unquote(url.fragment) not in documents[target].ids:
                errors.append(f"{path.relative_to(directory)} -> missing anchor {value}")
            checked += 1
    banned_names = {".git", ".env", ".aws", "node_modules", "experiments", "research/upstream"}
    allowed_roots = {"index.html", "styles.css", "app.js", ".nojekyll", "assets", "paper", "examples"}
    for path in directory.rglob("*"):
        relative = path.relative_to(directory)
        if path.is_symlink() or set(relative.parts) & banned_names or relative.parts[0] not in allowed_roots:
            errors.append(f"Unsafe artifact entry: {relative}")
        if path.is_file() and path.suffix in {".html", ".js", ".json", ".txt", ".vtt", ".css"}:
            if re.search(r"workflow-learning-lab|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY|sk-[A-Za-z0-9]{20,}", path.read_text()):
                errors.append(f"Private-name/secret-pattern match: {relative}")
    report = json.loads((directory / "examples/simulation/report.json").read_text())
    assert report["synthetic"] and report["mode"] == "offline-recorded"
    assert report["live_request_attempts"] == 0 and report["answer"]["answer_evidence_id"] == "e006"
    size = sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
    if size > 15 * 1024 * 1024:
        errors.append("Static artifact exceeds the 15 MiB media budget.")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {len(documents)} HTML documents, {checked} local references, {size:,} bytes; project-path and publication checks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    check(parser.parse_args().directory)
