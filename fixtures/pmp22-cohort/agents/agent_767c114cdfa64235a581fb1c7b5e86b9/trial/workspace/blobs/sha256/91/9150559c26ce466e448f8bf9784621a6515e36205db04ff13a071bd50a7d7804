"""Read-only review of preserved annotation and forum evidence for an endpoint handoff."""

import gzip
import hashlib
import json
import os
from itertools import islice
from pathlib import Path
import subprocess

Q = Path(__file__).resolve().parents[1]
OUT = Q / "outputs"
W = Path(os.environ["BIO_WORKSPACE"])


def load(path):
    return json.loads(path.read_text())


receipt = load(OUT / "execution-screen-r002.json")
assert receipt["complete"] and receipt["exit_code"] == 0
assert hashlib.sha256((Q / "scripts/screen.py").read_bytes()).hexdigest() == receipt["code_sha256"]
for name in ("pmp22-transcript-annotation.json", "pmp22-peak-sites.tsv"):
    native = OUT / "screen-r001" / name
    expected = next(r["sha256"] for r in receipt["outputs"] if Path(r["path"]).name == name)
    assert hashlib.sha256(native.read_bytes()).hexdigest() == expected
    print("VERIFIED EXISTING OUTPUT", name, expected)

source = load(Q / "inputs/http/gencode19-encode-gtf-r001.receipt.json")
source_path = W / "blobs/sha256" / source["sha256"][:2] / source["sha256"]
assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source["sha256"]
print("SOURCE", source["url"], source["sha256"])
with gzip.open(source_path, "rt") as handle:
    print("SOURCE HEADER", "".join(islice(handle, 5)))

features = load(OUT / "screen-r001/pmp22-transcript-annotation.json")
txs = [f for f in features if f["feature"] == "transcript"]
assert len(txs) == 8
print("ANNOTATION TRANSCRIPTS", len(txs), "DISTINCT LOWER BOUNDARIES", len({t["start"] for t in txs}))
for tx in txs:
    txid = tx["attrs"]["transcript_id"]
    exons = [f for f in features if f["feature"] == "exon" and f["attrs"]["transcript_id"] == txid]
    terminal = min(exons, key=lambda r: r["start"])
    print(txid, tx["attrs"]["transcript_type"],
          "span0", [tx["start"], tx["end"]],
          "terminal_exon0", [terminal["start"], terminal["end"]],
          "annotated_terminal_base1", tx["start"] + 1)

for term in ("gencode", "cleavage", "flair"):
    result = load(OUT / f"ends-coordinates-search-{term}-r001.json")
    print("SEARCH", term, "total", result["total"], "next_offset", result["next_offset"])
    for item in result["items"]:
        print(item["subject"], item["title"], "superseded_by", item["superseded_by"])
        print(item["summary"][:500])

peer = load(OUT / "ends-coordinates-peer-readback-r001.json")
print("PEER CURRENT DISCUSSION", peer["id"], "superseded_by", peer["superseded_by"], "replies", peer["replies"])
peer_manifest = load(Q / "inputs/community-reuse/artifact_1dc56cde62ec0f2c595bb2ccdb71d1259b3c4dec85cda82a2ec057ab5761b9b7.manifest.json")
blob = peer_manifest["output_blob"]
peer_bytes = (W / "blobs/sha256" / blob[:2] / blob).read_bytes()
assert hashlib.sha256(peer_bytes).hexdigest() == blob
print("VERIFIED PEER MAP", blob)
print(peer_bytes.decode())

artifact = load(OUT / "registrations-screen-r002/pmp22-transcript-annotation.json.registration.json")["artifact"]
command = ["./bin/bio", "--workspace", str(Path(os.environ["BIO_COMMUNITY"]) / "library"), "artifact", "show", artifact]
result = subprocess.run(command, text=True, capture_output=True, check=False)
check = {"command": command, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
(OUT / "ends-coordinates-shared-annotation-check-r001.json").write_text(json.dumps(check, indent=2))
if result.returncode:
    print("SHARED ANNOTATION LOOKUP", result.returncode, result.stdout, result.stderr)
else:
    shown = json.loads(result.stdout)
    assert shown["output_blob"] == "65f69c1d331ed092e0e6a8250226238e5ea187c24e632027ca9f6c5454aa73f4"
    print("SHARED ANNOTATION AVAILABLE", shown["id"], shown["output_blob"])
