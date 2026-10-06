"""Map only published RBP sites, summarize end perturbations and check annotations."""

import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import statistics

q = Path(__file__).resolve().parents[1]
o = q / "outputs"
w = Path(os.environ["BIO_WORKSPACE"]) / "blobs/sha256"
x = json.loads((q / "inputs/extension-manifest.json").read_text())
base = json.loads((q / "inputs/frozen-manifest-r001.json").read_text())


def blob(h):
    p = w / h[:2] / h
    assert hashlib.sha256(p.read_bytes()).hexdigest() == h
    return p


def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


def save(name, value):
    (o / name).write_text(json.dumps(value, indent=2, allow_nan=False))


def table(name, records):
    with (o / name).open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(records)


receipt = json.loads((o / "execution-ends-r004.json").read_text())
assert receipt["complete"] and receipt["exit_code"] == 0
for out in receipt["outputs"]:
    assert out["written"] and hashlib.sha256(Path(out["path"]).read_bytes()).hexdigest() == out["sha256"]
# Chain data are native UCSC alignment blocks, not downloaded executable code.
blocks = []
with gzip.open(blob(x["hg19ToHg38-chain"]["sha256"]), "rt") as f:
    for line in f:
        a = line.split()
        if not a:
            continue
        if a[0] == "chain":
            assert a[4] == "+"
            srcchrom, dstchrom, orientation = a[2], a[7], a[9]
            t, u, qsize, chain_id = int(a[5]), int(a[10]), int(a[8]), a[12]
        else:
            size = int(a[0])
            if srcchrom == "chr17":
                blocks.append((t, t + size, u, qsize, dstchrom, orientation, chain_id))
            if len(a) == 3:
                t += size + int(a[1])
                u += size + int(a[2])


def lift(start, end):
    hits = []
    for t0, t1, u0, qsize, chrom, orientation, chain_id in blocks:
        if t0 <= start and end <= t1:
            if orientation == "+":
                lo, hi = u0 + start - t0, u0 + end - t0
                assert lo - u0 + t0 == start and hi - u0 + t0 == end
            else:
                lo, hi = qsize - (u0 + end - t0), qsize - (u0 + start - t0)
                assert qsize - hi - u0 + t0 == start
                assert qsize - lo - u0 + t0 == end
            assert hi - lo == end - start
            hits.append((chrom, lo, hi, orientation, chain_id))
    return hits


sites = rows(blob(x["peer_sites"]["sha256"]))
models = rows(o / "transcript-site-map.tsv")
site_rows = []
selection = json.loads(blob(x["selection-r001.json"]["sha256"]).read_text())
for r in sites:
    s, e = int(r["start"]), int(r["end"])
    key = f"file-{r['source_file']}-r001"
    native = gzip.decompress(blob(x[key]["sha256"]).read_bytes()).decode()
    exact = [
        a
        for a in csv.reader(io.StringIO(native), delimiter="\t")
        if a[0] == r["chrom"] and int(a[1]) == s and int(a[2]) == e and a[5] == r["strand"]
    ]
    assert len(exact) == 1
    assert float(exact[0][6]) == float(r["signal_column7"])
    assert float(exact[0][7]) == float(r["negative_log10p_column8"])
    sel = [
        v for v in selection if v["role"] == "idr_peaks" and v["file"]["File accession"] == r["source_file"]
    ]
    assert len(sel) == 1 and sel[0]["cell"] == r["cell"] and sel[0]["rbp"] == r["rbp"]
    hits = lift(s, e)
    assert len(hits) == 1, (r, hits)
    chrom, lo, hi, orientation, chain_id = hits[0]
    assert chrom == "chr17" and orientation == "+"
    kept = []
    ambiguous = []
    for model in models:
        ep = json.loads(model["exon_path_native"])
        literal = any(a <= lo + 1 and b >= hi for a, b in ep)
        shifted = any(a + 1 <= lo + 1 and b >= hi for a, b in ep)
        if literal != shifted:
            ambiguous.append(model['transcript_id'])
        if literal and shifted:
            kept.append(model["transcript_id"])
    d = {
        **r,
        "source_assembly": "hg19",
        "coordinate_convention": "zero_based_half_open",
        "mapped_assembly": "hg38",
        "mapped_chrom": chrom,
        "mapped_start0": lo,
        "mapped_end0": hi,
        "chain_id": chain_id,
        "single_block_full_length_roundtrip": True,
        "n_flair_models_containing_full_peak": len(kept),
        "flair_models_containing_full_peak": ";".join(kept),
        "one_base_boundary_ambiguous_models": ";".join(ambiguous),
        "full_peak_containment_rule": "both native-GTF and start+1 conventions; disagreement retained as ambiguous",
    }
    for cut in [15229780, 15230714, 15230826]:
        # Minus-strand transcript retaining sequence from cleavage coordinate upwards.
        d[f"retention_if_cleavage_{cut}"] = (
            "full" if lo >= cut - 1 else ("absent" if hi <= cut - 1 else "partial")
        )
    site_rows.append(d)
# Annotation-only transcript ends are separately counted, never observed isoform counts.
anno = []
gencode_rows = []
with gzip.open(blob(x["gencode19-encode-gtf-r001"]["sha256"]), "rt") as f:
    for line in f:
        if line.startswith("#"):
            continue
        a = line.rstrip().split("\t")
        if 'gene_name "PMP22"' not in a[-1]:
            continue
        gencode_rows.append(line)
        attrs = dict(re.findall(r'(\w+) "([^"]*)"', a[-1]))
        if a[2] == "transcript":
            start0, end0 = int(a[3]) - 1, int(a[4])
            hits = lift(start0, start0 + 1)
            anno.append(
                {
                    "source": "GENCODE19",
                    "assembly": "hg19",
                    "transcript_id": attrs["transcript_id"],
                    "strand": a[6],
                    "annotated_start0": start0,
                    "annotated_end0": end0,
                    "annotated_threeprime_1": start0 + 1,
                    "mapped_threeprime_hg38_1": hits[0][1] + 1 if len(hits) == 1 else None,
                    "observational_status": "annotation_only_not_measured_usage",
                }
            )
assert len(anno) == 8
contemporary = json.loads(blob(base["ensembl-PMP22"]["blob"]).read_text())
for t in contemporary["Transcript"]:
    anno.append(
        {
            "source": "Ensembl_current_snapshot",
            "assembly": "GRCh38",
            "transcript_id": t["id"] + "." + str(t["version"]),
            "strand": "-",
            "annotated_start0": t["start"] - 1,
            "annotated_end0": t["end"],
            "annotated_threeprime_1": t["start"],
            "mapped_threeprime_hg38_1": t["start"],
            "observational_status": "annotation_only_not_measured_usage",
        }
    )
# Positive control and response summaries: no TPM-derived molecule CIs, no pairing assumption.
pc = rows(o / "paperclip-perturbation.tsv")
contrasts = []
for context in ["HeLa cells", "LN229 cells"]:
    control = [r for r in pc if r["source_context"] == context and r["treatment_native"] == "si-Ctrl"]
    assert len(control) == 2
    for condition in ["si-CFIm68", "si-CstF64/64tau"]:
        treat = [r for r in pc if r["source_context"] == context and condition in r["source_title"]]
        assert len(treat) == 2
        pctrl = [float(r["retaining_fraction"]) for r in control]
        ptrt = [float(r["retaining_fraction"]) for r in treat]
        cctrl = [float(r["SERPINE1_most_distal_cluster_fraction"]) for r in control]
        ctrt = [float(r["SERPINE1_most_distal_cluster_fraction"]) for r in treat]
        strict = [r for r in treat if r["treatment_native"] == condition]
        contrasts.append(
            {
                "context": context,
                "condition_from_source_title": condition,
                "control_ids": [r["gsm"] for r in control],
                "treated_ids": [r["gsm"] for r in treat],
                "n_control_independent_experiments_source": 2,
                "n_treated_independent_experiments_source": 2,
                "PMP22_retaining_control": pctrl,
                "PMP22_retaining_treated": ptrt,
                "PMP22_mean_retaining_delta_percentage_points": 100
                * (statistics.mean(ptrt) - statistics.mean(pctrl)),
                "SERPINE1_distal_control": cctrl,
                "SERPINE1_distal_treated": ctrt,
                "SERPINE1_mean_distal_delta_percentage_points": 100
                * (statistics.mean(ctrt) - statistics.mean(cctrl)),
                "native_treatment_discrepancies": [
                    {"gsm": r["gsm"], "title": r["source_title"], "treatment": r["treatment_native"]}
                    for r in treat
                    if r not in strict
                ],
                "strict_native_label_sensitivity_n": len(strict),
                "strict_native_label_PMP22_delta_percentage_points": 100
                * (statistics.mean(float(r["retaining_fraction"]) for r in strict) - statistics.mean(pctrl)),
            }
        )
poly = rows(o / "polyasite-usage.tsv")
sens = []
for threshold in [0.1, 1, 5]:
    eligible = [r for r in poly if float(r["all6_terminal_tpm"]) >= threshold]
    vals = [float(r["all6_retaining_fraction"]) for r in eligible]
    sens.append(
        {
            "all6_min_tpm": threshold,
            "n_libraries": len(vals),
            "min_retaining": min(vals),
            "n_ge_0.95": sum(v >= 0.95 for v in vals),
        }
    )
protocols = []
for protocol in sorted({r["protocol_label"] for r in poly}):
    eligible = [r for r in poly if r["protocol_label"] == protocol and float(r["terminal_tpm"]) >= 1]
    if eligible:
        protocols.append(
            {
                "protocol": protocol,
                "n_eligible": len(eligible),
                "n_ge_0.95": sum(float(r["retaining_fraction"]) >= 0.95 for r in eligible),
                "minimum_retaining": min(float(r["retaining_fraction"]) for r in eligible),
            }
        )
# The one >=5% discovery exception stays visible; inspect its companion libraries descriptively.
k562 = [r for r in poly if r["source_context"] == "K562" and r["protocol_label"] == "DRS"]
for r in k562:
    r["retaining_fraction"] = float(r["retaining_fraction"]) if r["retaining_fraction"] else None
summary = {
    "PAPERCLIP_contrasts_retrospective": contrasts,
    "all6_site_sensitivity": sens,
    "protocol_sensitivity": protocols,
    "K562_DRS_exception_and_companions": k562,
    "annotation_counts": {
        "GENCODE19_transcripts": sum(r["source"] == "GENCODE19" for r in anno),
        "GENCODE19_distinct_annotated_threeprime_positions": len(
            {r["annotated_threeprime_1"] for r in anno if r["source"] == "GENCODE19"}
        ),
    },
    "native_RBP_sites_checked": len(site_rows),
    "RBP_liftover_checks": "all8 full-length unique single-block, inverse and width checked; source data not a new binding experiment",
    "novelty": "miR29/deletion and QKI are recovered mechanisms; atlas/FLAIR structures previously public; quantitative retention/perturbation comparison is this question reanalysis, not established novel biology",
    "independence": "PAPERCLIP HeLa/LN229 are same study/context corroboration; GTEx is separate resource/assay but model-filtered, not unbiased APA replication; K562 cell line occurs in both, not assumed independent donor evidence",
}
table("rbp-end-availability.tsv", site_rows)
table("annotation-only-ends.tsv", anno)
save("end-response-and-rbp.json", summary)
(o / "gencode19-PMP22-native.gtf").write_text("".join(gencode_rows))
print(json.dumps(summary, indent=2))
for r in site_rows:
    print(
        "RBP_MAP",
        r["rbp"],
        r["mapped_start0"],
        r["mapped_end0"],
        [r[f"retention_if_cleavage_{p}"] for p in [15229780, 15230714, 15230826]],
    )
