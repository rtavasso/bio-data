"""Verify and format existing coverage products; do not rerun matrix analysis."""
import csv
import hashlib
import json
from pathlib import Path

question = Path(__file__).resolve().parents[1]
out = question / "outputs"
receipt = json.loads((out / "rbp-coverage-execution-r002.json").read_text())
assert receipt["exit_code"] == 0 and receipt["complete"]
producer = question / "scripts" / Path(receipt["producer"]).name
assert hashlib.sha256(producer.read_bytes()).hexdigest() == receipt["code_sha256"]
for item in receipt["outputs"]:
    local = out / Path(item["path"]).name
    assert hashlib.sha256(local.read_bytes()).hexdigest() == item["sha256"]
summary = json.loads((out / "rbp-coverage-summary.json").read_text())
with (out / "rbp-coverage-samples.tsv").open() as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
for item in summary["coverage"]:
    subset = [r for r in rows if r["dataset"] == item["dataset"] and r["gene_requested"] == item["gene_requested"]]
    assert len(subset) == item["sample_count"]
    assert len({r["accession"] for r in subset}) == item["sample_count"]
    if item["native_exact_symbol_present"]:
        assert all(r["status"] == "measured" for r in subset)
        values = [float(r["cpm"]) for r in subset]
        assert min(values) == item["minimum_cpm"]
        assert max(values) == item["maximum_cpm"]
        display = f"{min(values):.2f}-{max(values):.2f}"
    else:
        assert all(r["status"] == "native_exact_symbol_unmapped" and r["cpm"] == "" and r["native_count"] == "" for r in subset)
        assert item["minimum_cpm"] is None and item["maximum_cpm"] is None
        display = "unmapped, not zero; native alternative " + ",".join(item["alternative_Qk_prefix_tokens_not_mapped"])
    print(item["dataset"], item["gene_requested"], item["sample_count"], display, sep="\t")
print("Verified original producer/output hashes and all saved coverage summaries against per-sample rows.")
print("Sample map:")
for row in rows:
    if row["gene_requested"] == "Pmp22":
        print(row["dataset"], row["accession"], row["source_title"], sep="\t")
