"""Read saved results for a coordination reply; do not rerun scientific producers."""

import csv
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

artifact_log = Path(
    ".hermes/cache/terminal-output/out-1791245492-43284-1220.log"
)
for line in artifact_log.read_text().splitlines():
    if not line.startswith('{"created":'):
        continue
    record = json.loads(line)
    name = record["manifest"]["output"]["name"]
    path = OUT / "screen-r001" / name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == record["output_blob"], (name, digest)
    print("VERIFIED ARTIFACT", record["id"], name, digest)

with (OUT / "screen-r001/binding-by-perturbation.tsv").open() as stream:
    rows = list(csv.DictReader(stream, delimiter="\t"))
assert len(rows) == 223
paired = [r for r in rows if r["rna_status"] == "measured"]
assert len(paired) == 203
for cell in ("HepG2", "K562"):
    values = [float(r["pmp22_baseMean"]) for r in paired if r["cell"] == cell]
    print("COVERAGE REVIEW", cell, "contrasts", len(values), "median", median(values),
          "below20", sum(v < 20 for v in values))
columns = [
    "rbp", "eclip_experiment", "eclip_control", "peak_file", "assembly",
    "rna_experiment", "rna_control", "de_file", "pmp22_baseMean",
    "pmp22_log2FoldChange", "pmp22_padj", "ci95_lower", "ci95_upper",
    "adequate_target_rna_depletion",
]
for row in rows:
    if row["binding_status"] == "selected_reproducible_peak":
        print("BINDER REVIEW", json.dumps({k: row[k] for k in columns}))

replicates = json.loads((ROOT / "inputs/views/PUM2-replicates.json").read_text())
for rep in replicates:
    lib = rep["library"]
    sample = lib["biosample"]
    print("PUM2 RNA SAMPLE", json.dumps({
        "experiment": rep["experiment"],
        "biological_replicate_number": rep.get("biological_replicate_number"),
        "technical_replicate_number": rep.get("technical_replicate_number"),
        "library": lib["accession"],
        "biosample": sample["accession"],
    }))

for stem in ("isr", "polysome"):
    record = json.loads((OUT / f"translation-site-search-{stem}-r001.json").read_text())
    print("FORUM SEARCH", stem, "total", record["total"], "next_offset", record["next_offset"])
    for item in record["items"]:
        print(item["subject"], item["title"], item["summary"][:700],
              "SUPERSEDED_BY", item["superseded_by"])

for stem in ("end", "fate"):
    record = json.loads((OUT / f"translation-site-peer-{stem}-r001.json").read_text())
    print("PEER DISCUSSION", record["id"], "superseded_by", record["superseded_by"])
    print(record["content"]["body"])
    print("REPLIES", record["replies"])

peer = json.loads((OUT / "translation-site-peer-effects-manifest-r001.json").read_text())
peer_path = Path(peer["path"])
peer_bytes = peer_path.read_bytes()
assert hashlib.sha256(peer_bytes).hexdigest() == peer["output_blob"]
print("PEER EFFECT ARTIFACT VERIFIED", peer["id"], peer["output_blob"])
print("PEER OUTPUT DEFINITION", json.dumps(peer["manifest"]["output"]))
print("PEER EFFECT TABLE", peer_bytes.decode())
