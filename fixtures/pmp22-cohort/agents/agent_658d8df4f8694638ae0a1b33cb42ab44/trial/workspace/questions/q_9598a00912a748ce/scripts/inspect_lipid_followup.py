"""Bounded review of existing community evidence; no scientific source acquisition."""
import hashlib
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = "b55936c627d1258eb98aeee04f0f6fb86affc5969b3fd289d25a0ae37fdbd32e"
source = Path(os.environ["BIO_COMMUNITY"]) / "library/blobs/sha256" / SHA[:2] / SHA
raw = source.read_bytes()
assert hashlib.sha256(raw).hexdigest() == SHA


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.suppressed += 1
        if tag in {"p", "section", "h1", "h2", "h3", "h4", "figcaption", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.suppressed -= 1
        if tag in {"p", "section", "h1", "h2", "h3", "h4", "figcaption", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


parser = Text()
parser.feed(raw.decode())
lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
lines = [line for line in lines if line]
(ROOT / "outputs/lipid-followup-primary-text.txt").write_text("\n".join(lines) + "\n")
print("PRIMARY EXISTING SOURCE HASH VERIFIED", SHA)
for i, line in enumerate(lines, 1):
    if any(term in line.lower() for term in ["endoh", "endo h", "10-month", "shrna", "neonatal"]):
        print(f"SOURCE LINE {i}: {line}")

seen = set()
review = []
for term in ["ABCA1", "cholesterol", "EndoH", "GSE252209", "GSE115930"]:
    data = json.loads((ROOT / f"inputs/community/followup-{term}.json").read_text())
    items = data["items"]
    header = f"SEARCH {term}: total={data.get('total')}, returned={len(items)}, next_offset={data.get('next_offset')}"
    review.append(header)
    print(header)
    for item in items:
        subject = item["subject"]
        if subject in seen:
            continue
        seen.add(subject)
        review.append(f"\n{subject} {item['title']} superseded_by={item.get('superseded_by')}")
        review.append(item.get("summary", ""))
        print(subject, item["title"], "superseded", item.get("superseded_by"))
(ROOT / "outputs/lipid-followup-community-review.txt").write_text("\n".join(review) + "\n")
print("Unique reviewed search hits:", len(seen))
