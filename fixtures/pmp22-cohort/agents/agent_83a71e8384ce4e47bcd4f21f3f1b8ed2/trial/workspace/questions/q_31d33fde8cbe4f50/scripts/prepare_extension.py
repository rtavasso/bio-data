"""Prepare exact limited peer reuse and chain provenance, without executing peer code."""

import gzip
import hashlib
import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET

q = Path(__file__).resolve().parents[1]
w = Path(os.environ["BIO_WORKSPACE"]) / "blobs/sha256"


def blob(h):
    p = w / h[:2] / h
    assert hashlib.sha256(p.read_bytes()).hexdigest() == h
    return p


manifest_hash = "f094ca9d512a8815006fdc893389c6f091d99461a59a5bfd0376aad278860704"
x = json.loads(blob(manifest_hash).read_text())
selected = {}
for r in x["files"]:
    if any(
        k in r["name"]
        for k in [
            "ENCFF977MKB",
            "ENCFF298ZAG",
            "ENCFF331VCF",
            "ENCFF767LWE",
            "ENCFF027CBV",
            "gencode19-encode",
            "selection-r001",
        ]
    ):
        selected[r["name"]] = r
        print("SELECTED", r)
selected["peer_sites"] = {"sha256": "06d02d8b73a971a4e44118f92dd3525d4a363434876f3e5104054bb9a6885647"}
selected["peer_manifest"] = {"sha256": manifest_hash}
for label in ["hg19ToHg38-chain", "qki-primary-bioc"]:
    r = json.loads((q / "inputs/sources" / f"{label}.receipt.json").read_text())
    selected[label] = {"sha256": r["sha256"], "receipt": f"inputs/sources/{label}.receipt.json"}
(q / "inputs/extension-manifest.json").write_text(json.dumps(selected, indent=2))
root = ET.parse(blob(selected["qki-primary-bioc"]["sha256"])).getroot()
text = "\n\n".join(p.findtext("text", "") for p in root.findall(".//passage"))
(q / "inputs/sources/qki-primary-bioc.txt").write_text(text)
for p in text.split("\n\n"):
    if any(k in p for k in ["PMP22", "NM_000304", "polyadenylation", "available"]):
        print("QKI", p)
with gzip.open(blob(selected["hg19ToHg38-chain"]["sha256"]), "rt") as f:
    print("CHAIN_HEADER", next(f).rstrip())
