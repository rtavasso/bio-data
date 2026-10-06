"""Extract source passages from locally received primary text; no RNA analysis."""
import hashlib
import json
import re
import textwrap
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

q = Path(__file__).resolve().parents[1]
root = q / "sources" / "qki-live"
source = root / "PMC13234107-bioc.xml"
receipt = json.loads((root / (source.name + ".receipt.json")).read_text())
assert hashlib.sha256(source.read_bytes()).hexdigest() == receipt["sha256"]
tree = ET.fromstring(source.read_bytes())
sections = []
include_next = False
for number, passage in enumerate(tree.iter("passage"), 1):
    text = " ".join(passage.findtext("text", "").split())
    if include_next or re.search(r"PMP22|rMATS|primer|availability|Accession", text, re.I):
        sections.append(f"PASSAGE {number}; OFFSET {passage.findtext('offset', '')}\n"
                        + textwrap.fill(text, width=110) + "\n")
    include_next = text.lower() == "data availability"
(q / "outputs/qki-reviewed-passages.txt").write_text("\n".join(sections))


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ("p", "div", "br", "li", "dt", "dd", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


parser = TextOnly()
parser.feed((root / "NCBI-Gene5376.html").read_text())
text = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
(q / "outputs/qki-gene-page-text.txt").write_text(text)
gb = root / "human-PMP22-two-refseq.gb"
gb_receipt = json.loads((root / (gb.name + ".receipt.json")).read_text())
assert hashlib.sha256(gb.read_bytes()).hexdigest() == gb_receipt["sha256"]
records = []
for record in gb.read_text().split("//"):
    if "VERSION" not in record:
        continue
    lines = record.splitlines()
    selected = set()
    for index, line in enumerate(lines):
        if line.startswith(("LOCUS", "DEFINITION", "VERSION")) or "Transcript Variant:" in line:
            selected.update(range(index, min(index + 3, len(lines))))
    records.append("\n".join(lines[index] for index in sorted(selected)))
assert len(records) == 2
(q / "outputs/qki-refseq-records.txt").write_text("\n\n".join(records))
print(f"Extracted {len(sections)} article passages and the received gene-page text.")
