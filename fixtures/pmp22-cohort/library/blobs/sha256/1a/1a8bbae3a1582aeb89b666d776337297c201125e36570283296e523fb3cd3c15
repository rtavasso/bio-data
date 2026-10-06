"""Local-only consolidation audit. Rechecks inherited evidence, not a new biological test.

Never imports/executes inherited producer scripts or changes their outputs.
All paths in the audit are workspace-relative; catalog reads use the supplied CLI.
"""
import argparse
import csv
import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, variance

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from scipy.stats import t

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
ROOT = W.parent
U = Q / "outputs/upstream"
C = Q / "outputs/consolidation"
INPUTS = {}
CHECKS = []


def tracked(path):
    path = path.resolve()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    INPUTS[str(path.relative_to(W))] = digest
    return path


def load(path):
    return json.loads(tracked(path).read_text())


def check(label, passed, detail=None):
    CHECKS.append({"check": label, "passed": bool(passed), "detail": detail})
    assert passed, label


def cli(*args):
    p = subprocess.run([str(ROOT / "bin/bio"), *args], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def blob(digest):
    path = tracked(W / "blobs/sha256" / digest[:2] / digest)
    check("immutable_sha256:" + digest, INPUTS[str(path.relative_to(W))] == digest)
    return path


def exclusive(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--revision", type=int, required=True)
args = parser.parse_args()
C.mkdir(exist_ok=True)
label = f"r{args.revision:03d}"
result_path = C / f"verification-{label}.json"
assert not result_path.exists(), "Preserve previous verification; choose a new revision"
artifacts = {
    "artifact_1123b0484f0be58e323e908acbde06d4bd2378473bb961b7e36871afa225e274": U / "nae1-RNA-summary.json",
    "artifact_0f7ede8968ed0aba576c856ccef0022cb3cdae962cfc1bc2d2f92bd0172b83f9": U / "antioxidant-summary.json",
    "artifact_0ce2aca3b3d0f1f6230aa21d5cd4d5997c63cfeb0dc870e047a34cf245817e7f": U / "antioxidant-posthoc-summary.json",
    "artifact_67f1a8f71cf2a4978144bdf321e65bd485c719476e2a0a4c281a61f319c1e3eb": U / "analysis-package.r002.json",
    "artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a": Q / "outputs/prepared.parquet",
    "artifact_abee146fb898851d7990ccc5bce8cd7853e6998cdf03f02523f02a63ec2a88ed": Q / "outputs/specific/validation-summary-r003.json",
    "artifact_b11c4fbe0536a4c827c7ee65a1159591b70693787d55c2bdff98379724cddc43": Q / "outputs/context-audit/reference-sensitivity.tsv",
}
manifests = {}
for aid, local in artifacts.items():
    record = cli("artifact", "show", aid)
    manifests[aid] = record
    check("exact_output_name:" + aid, record["manifest"]["output"]["name"] == local.name)
    check("question_link:" + aid, any(v["question_id"] == Q.name for v in record["questions"]))
    output = blob(record["output_blob"])
    tracked(local)
    check("local_output:" + aid, INPUTS[str(local.relative_to(W))] == record["output_blob"])
    blob(record["manifest_blob"])
    derivation = record["manifest"]["derivation"]
    for entry in derivation["inputs"]:
        blob(entry["blob"])
    for digest in derivation["code"]:
        blob(digest)
    print(aid, record["output_role"], "output/input/code hashes and question link verified", flush=True)

# Eight original RSEM files versus the full saved matrix, then the existing normalization.
counts = pd.read_csv(tracked(U / "nae1-all-expected-counts.tsv"), sep="\t", index_col=0)
counts.pop("symbol")
for receipt in load(Q / "inputs/upstream/rna-fetch-receipts.json"):
    source = pd.read_csv(blob(receipt["receipt"]["blob"]), compression="gzip", sep="\t", index_col=0)
    sample = receipt["name"].split("_", 1)[1].split(".genes")[0]
    check("native_full_count_column:" + sample, source.index.equals(counts.index) and np.allclose(source.expected_count, counts[sample]))
positive = (counts > 0).all(axis=1)
geometric = np.exp(np.log(counts.loc[positive]).mean(axis=1))
factors = counts.loc[positive].div(geometric, axis=0).median()
normalized = np.log2(counts.div(factors, axis=1) + 0.5)
saved = pd.read_csv(tracked(U / "nae1-all-log2normalized.tsv"), sep="\t", index_col=0)
symbols = saved.pop("symbol")
check("complete_saved_normalization", np.allclose(normalized, saved, rtol=1e-10, atol=1e-10))
wt = [c for c in counts if c.startswith("WT_")]
ko = [c for c in counts if c.startswith("KO_")]
check("four_libraries_each_not_genes_as_replicates", len(wt) == len(ko) == 4)
raw = counts.copy()
raw.index = symbols
markers = ["Mpz", "Mbp", "Mag", "Prx", "Plp1", "Cnp", "Mal"]
log = np.log2(raw.loc[markers + ["Pmp22"]] + 0.5)
relative = log.loc["Pmp22"] - log.loc[markers].mean()
effect = mean(relative[ko]) - mean(relative[wt])
va = variance(relative[ko]) / len(ko)
vb = variance(relative[wt]) / len(wt)
df = (va + vb) ** 2 / (va ** 2 / (len(ko) - 1) + vb ** 2 / (len(wt) - 1))
radius = float(t.ppf(0.975, df) * math.sqrt(va + vb))
summary = load(U / "nae1-RNA-summary.json")
check("locked_nae1_effect_and_interval", np.allclose([effect, effect - radius, effect + radius], [summary["deltaR"], *summary["deltaR_uncertainty"]["ci95"]], rtol=1e-10))
check("nae1_rejection_retained", summary["eligibility_pass"] and not summary["passes_locked_rule"])
check("osgin1_native_low_count_not_missing_or_zero", float(raw.loc["Osgin1", wt].min()) == 1.0)

# Inspect native Excel cells without evaluating formulas, including the failed floor.
extraction = load(U / "Figlia-extraction.json")
xlsx = tracked(Q / extraction["output"])
check("figlia_native_hash", INPUTS[str(xlsx.relative_to(W))] == extraction["sha256"])
workbook = load_workbook(xlsx, read_only=True, data_only=False)
required = {"Pmp22", "Osgin1", "Nqo1", "Hmox1", "Gclc", "Gclm", *markers}
source_effects = pd.read_csv(tracked(U / "antioxidant-gene-effects.tsv"), sep="\t")
for group in ["TSC1KO", "PTENKO", "RaptorKO"]:
    rows = workbook["Control vs " + group].iter_rows(values_only=True)
    header = list(next(rows))
    target = [dict(zip(header, row, strict=True)) for row in rows if row[header.index("gene_name")] in required]
    check("unique_native_panel:" + group, len(target) == len(required))
    for row in target:
        gene = row["gene_name"]
        value = source_effects[(source_effects.study == group) & (source_effects.gene == gene)].source_effect.iloc[0]
        check("native_comparator_effect:" + group + ":" + gene, np.isclose(value, row["log2 Ratio"]))
        if gene == "Osgin1":
            baseline = [row[f"Dev{i} [normalized count]"] for i in [1, 2, 3]]
            check("osgin1_figlia_floor:" + group, min(baseline) == 9.412 and row["isPresent"] == "TRUE", baseline)
workbook.close()
antioxidant = load(U / "antioxidant-summary.json")
check("five_gene_test_untestable", antioxidant["status"] == "untestable" and not antioxidant["passes_locked_rule"])
posthoc = load(U / "antioxidant-posthoc-summary.json")
check("reduced_panel_exploratory", posthoc["status"] == "retrospective_exploratory_not_validation")
with tracked(U / "antioxidant-posthoc-source-cells.tsv").open() as stream:
    cells = list(csv.DictReader(stream, delimiter="\t"))
for study in ["Nae1KO", "TSC1KO", "PTENKO", "RaptorKO"]:
    scores = {}
    groups = {}
    for row in cells:
        if row["study"] == study and row["gene"] in ["Nqo1", "Hmox1", "Gclc", "Gclm"]:
            scores.setdefault(row["sample"], []).append(float(row["log2amount"]))
            groups[row["sample"]] = row["group"]
    check("four_genes_per_sample:" + study, all(len(v) == 4 for v in scores.values()))
    value = mean(mean(v) for s, v in scores.items() if groups[s] == "KO") - mean(mean(v) for s, v in scores.items() if groups[s] == "Control")
    expected = next(p for p in posthoc["panels"] if p["study"] == study and p["panel"] == "eligible4")
    check("eligible4_saved_cells:" + study, np.isclose(value, expected["effect"]), value)

records = {name: load(Q / "outputs" / name) for name in ["discoveries.json", "investigations.json", "mechanisms.json"]}
check("hormonal_deferred", next(i for i in records["investigations.json"]["items"] if i["id"] == "hormonal-metabolic-coverage")["status"] == "deferred")
check("all_three_rejections_retained", all(r["status_under_lock"] == "contradicted" for r in load(Q / "outputs/specific/validation-summary-r003.json")["primary_results"]))
for prediction, receipt in [("prediction-r001.json", "prediction-seal-receipt.json"), ("antioxidant-prediction-r001.json", "antioxidant-seal-receipt.json")]:
    path = tracked(U / prediction)
    check("unchanged_seal:" + prediction, INPUTS[str(path.relative_to(W))] == load(U / receipt)["sha256"])
command = [str(ROOT / "bin/python"), "-m", "daw.research_records", str(Q)]
proc = subprocess.run(command, capture_output=True, text=True, check=True)
record_check = json.loads(proc.stdout)
check("full_research_records", record_check["valid"] and not record_check["errors"], record_check)
exclusive(C / f"full-record-check-{label}.json", record_check)
exclusive(C / f"artifact-readbacks-{label}.json", manifests)
result = {
    "question": Q.name, "revision": args.revision, "checked_at": datetime.now(UTC).isoformat(),
    "scope": "Local consolidation verification of inherited outputs. Not new measurements, independent biological validation, novelty or causal adjudication.",
    "valid": True, "checks_passed": len(CHECKS), "checks": CHECKS,
    "records": {name: {"revision": rec["revision"], "sha256": INPUTS[str((Q / "outputs" / name).relative_to(W))]} for name, rec in records.items()},
    "artifact_ids": list(artifacts), "inputs": INPUTS,
    "verified_values": {"nae1_deltaR": effect, "nae1_ci95": [effect - radius, effect + radius]},
}
exclusive(result_path, result)
print(json.dumps({"valid": True, "checks_passed": len(CHECKS), "artifacts_checked": len(artifacts), "input_files": len(INPUTS), "verification": str(result_path.relative_to(W))}, indent=2))
