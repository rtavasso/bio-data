"""Inspect preserved peer source text; do not execute imported code or rerun RNA."""

import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
ZIP_HASH = "7524526ad81bc922edf72c61f7e179710b3a746a24ec8d88a383104279988212"
DESIGN_HASH = "0657e6defd3ff6c865519cd66f987af4ec284e22473f0efd05d379ea00fc4a23"


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in {"p", "h1", "h2", "h3", "h4", "figure", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)
        if tag in {"p", "h1", "h2", "h3", "h4", "figure", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def verified_blob(digest):
    path = WORKSPACE / "blobs" / "sha256" / digest[:2] / digest
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest
    return path


zip_path = verified_blob(ZIP_HASH)
verified_blob(DESIGN_HASH)
with ZipFile(zip_path) as archive:
    source = archive.read("sources/PMC5181599.html")
parser = TextParser()
parser.feed(source.decode("utf-8"))
text = "\n".join(
    line for raw in "".join(parser.parts).splitlines()
    if (line := " ".join(raw.split()))
)
(ROOT / "outputs" / "mechanics-followup-PMC5181599.txt").write_text(text + "\n")
receipt = {
    "operation": "local preserved-source inspection; no scientific reanalysis",
    "zip_sha256_verified": ZIP_HASH,
    "design_sha256_verified": DESIGN_HASH,
    "source_member": "sources/PMC5181599.html",
    "source_sha256": hashlib.sha256(source).hexdigest(),
    "source_title_found": "Tead1 regulates the expression of Peripheral Myelin Protein 22" in text,
    "downloaded_code_executed": False,
}
assert receipt["source_title_found"]
(ROOT / "outputs" / "mechanics-followup-inspection.json").write_text(
    json.dumps(receipt, indent=2, allow_nan=False) + "\n"
)
print(json.dumps(receipt, indent=2, allow_nan=False))
