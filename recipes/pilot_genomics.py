"""Native-reference locus queries across a repository-discovered human track and rat ATAC peaks.

The inspected regions are annotated gene spans, explicitly not complete regulatory domains.
No promoter identity, liftover, cross-species comparison, or binding-to-regulation inference.
"""
import csv
import re

from daw.adapters import Sources
from daw.catalog import Workspace
from daw.curation import accept, add_assertion, register_reference
from daw.inspectors import extract_members
from daw.models import AssertionInput, Curation, Evidence, Query, Region
from daw.query import query, render_report
from daw.util import DawError, now, read_json, write_json


def field(ws, asset, name, value, raw, blob, locator, method):
    return add_assertion(ws, AssertionInput(subject=asset["resource_id"], field=name, raw_value=raw, value=value,
        evidence=Evidence(blob=blob, locator=locator, method=method)))


def build_reference(ws, assembly, species, genes):
    sizes = next(a for a in ws.assets() if a["body"]["name"] == assembly + ".chrom.sizes" and a["blob"])
    annotation = next(a for a in ws.assets() if a["body"].get("url") and
                      f"/{assembly}/database/refGene.txt.gz" in a["body"]["url"] and a["blob"])
    child = extract_members(ws, annotation["id"], ["refGene.txt"])[0]
    source = ws.blob_path(sizes["blob"]).read_text()
    chroms = {line.split()[0]: int(line.split()[1]) for line in source.splitlines()}
    ref = {"assembly": assembly, "species": species, "chromosomes": chroms, "aliases": {},
           "namespaces": ["UCSC contig", "RefSeq transcript accession", "source gene symbol"],
           "annotation": {"source": annotation["body"]["url"], "release": "UCSC refGene snapshot 2026-09-27",
                          "blob": annotation["blob"], "decompressed_blob": child["blob"]},
           "evidence": [{"blob": sizes["blob"], "locator": "lines:1-1"}],
           "contig_source_snapshot": sizes["snapshot_id"], "annotation_source_snapshot": annotation["snapshot_id"]}
    ref_hash = register_reference(ws, ref)["reference"]
    by_gene = {gene: [] for gene in genes}
    with ws.blob_path(child["blob"]).open() as stream:
        for number, fields in enumerate(csv.reader(stream, delimiter="\t"), 1):
            if len(fields) >= 16 and fields[12] in by_gene:
                by_gene[fields[12]].append({"row": number, "transcript": fields[1], "chrom": fields[2],
                                          "start": int(fields[4]), "end": int(fields[5]), "strand": fields[3]})
    domains = {}
    for gene, records in by_gene.items():
        primary = [r for r in records if re.fullmatch(r"chr(?:\d+|X|Y|M)", r["chrom"])]
        if not primary or len({r["chrom"] for r in primary}) != 1:
            raise DawError("ambiguous_annotation_locus", gene)
        region = Region(chrom=primary[0]["chrom"], start=min(r["start"] for r in primary), end=max(r["end"] for r in primary), reference=ref_hash)
        body = {"name": gene, "region": region.model_dump(), "method": "union of primary-chromosome annotated transcript spans",
                "uncertainty": "provisional gene-span inspection region; not a complete regulatory domain or promoter definition",
                "annotation_blob": child["blob"], "annotation_rows": records, "excluded_alternate_contigs": len(records) - len(primary)}
        domain = ws.put_json(body)
        ws.resource("domain", "curated", domain, {"blob": domain})
        domains[gene] = {"domain": domain, "region": region.model_dump()}
    return ref_hash, domains


def run(ws):
    references, domains = {}, {}
    for assembly, species, genes in (("hg38", "Homo sapiens", ["PMP22", "SOX10"]), ("rn6", "Rattus norvegicus", ["Pmp22", "Sox10"])):
        references[assembly], domains[assembly] = build_reference(ws, assembly, species, genes)
    accepted, outcomes = [], []
    chip = [a for a in ws.assets() if a["body"]["metadata"].get("genome") == "hg38" and a["blob"]]
    bw = next(a for a in chip if a["body"]["name"] == "SRX24150189.bw")
    native = bw["body"]["metadata"]["source_metadata"]
    listing = ws.one("SELECT snapshot_id FROM asset_revision WHERE resource_id=? AND access='listed' ORDER BY created DESC LIMIT 1",
                     (bw["resource_id"],))
    snapshot = ws.one("SELECT blob FROM snapshot WHERE id=?", (listing["snapshot_id"],))
    metadata_blob = snapshot["blob"]
    source_data = read_json(ws.blob_path(metadata_blob))
    index = next(i for i, row in enumerate(source_data) if row["genome"] == "hg38")
    docs_blob = bw["body"]["metadata"]["download_rule_blob"]
    docs = ws.blob_path(docs_blob).read_text()
    rpm_quote = "RPM (Reads Per Million mapped reads)"
    if rpm_quote not in docs:
        raise DawError("source_units_quote_changed")
    settings = {"units": "RPM", "signal_missingness": "covered_bases_only", "target": native["agSubClass"],
                "assay": native["title"], "biological_context": native["attributes"]}
    assertions = {
        "reference": field(ws, bw, "reference", references["hg38"], "hg38", metadata_blob, f"/{index}/genome", "exact source assembly to pinned UCSC reference"),
        "units": field(ws, bw, "units", "RPM", rpm_quote, docs_blob, "text:" + rpm_quote, "source processing units"),
        "signal_missingness": field(ws, bw, "signal_missingness", "covered_bases_only", rpm_quote, docs_blob, "text:" + rpm_quote,
                                    "conservative operator policy: extract exact mean only where native intervals exist"),
        "target": field(ws, bw, "target", native["agSubClass"], native["agSubClass"], metadata_blob, f"/{index}/agSubClass", "native target retained with antibody attributes"),
        "assay": field(ws, bw, "assay", native["title"], native["title"], metadata_blob, f"/{index}/title", "unaltered source assay title"),
        "biological_context": field(ws, bw, "biological_context", native["attributes"], native["attributes"], metadata_blob,
                                    f"/{index}/attributes", "unaltered original sample and antibody attributes"),
    }
    accepted.append(accept(ws, Curation(asset_revision=bw["id"], kind="signal", settings=settings, assertions=assertions,
        reference=references["hg38"], limitations=["H3K27ac ChIP-seq in engineered immortalized human Schwann cells, NF1 proficient/SUZ12 deficient",
        "Descriptive native RPM; not a direct regulatory effect or comparison to rodent assays"])))
    thresholds = {}
    for code in ("05", "20"):
        asset = next(a for a in chip if a["body"]["name"] == f"SRX24150189.{code}.bed")
        rows = []
        with ws.blob_path(asset["blob"]).open() as f:
            for line in f:
                if line.startswith(("track", "#", "browser")) or not line.strip():
                    continue
                parts = line.split()
                if len(parts) != 10:
                    raise DawError("unexpected_chipatlas_peak_schema", "reviewed fixture requires narrowPeak ten columns")
                rows.append(parts)
        rule = Sources.chipatlas_threshold(code)
        thresholds[code] = {"blob": asset["blob"], "rule": rule, "rows": len(rows),
                            "schema": "narrowPeak10", "qvalue_column": 9,
                            "minimum_qvalue": min(float(r[8]) for r in rows), "intervals": [r[:3] for r in rows]}
    nested = {tuple(x) for x in thresholds["20"]["intervals"]} <= {tuple(x) for x in thresholds["05"]["intervals"]}
    contained = all(any(a[0] == b[0] and int(a[1]) <= int(b[1]) and int(a[2]) >= int(b[2])
                        for a in thresholds["05"]["intervals"]) for b in thresholds["20"]["intervals"])
    valid = contained and all(v["minimum_qvalue"] >= v["rule"]["minimum_qvalue"] for v in thresholds.values())
    threshold_receipt = {"source": "processing wiki and exact per-experiment BED files", "thresholds": thresholds,
                         "stricter_is_exact_row_subset": nested, "strict_intervals_contained_in_loose_intervals": contained,
                         "validated": valid, "retrieved_utc": now(),
                         "interpretation": "all strict peaks meet their native Q cutoff and are contained in loose peaks; changed boundaries mean this is not row filtering",
                         "agent_guide_disagreement": "smaller-is-stricter wording not applied to encoded file thresholds"}
    threshold_blob = ws.put_json(threshold_receipt)
    write_json("docs/receipts/chipatlas-threshold-check.json", {**threshold_receipt, "thresholds": {
        k: {x: y for x, y in v.items() if x != "intervals"} for k, v in thresholds.items()}, "artifact": threshold_blob})
    # Rat ATAC eligibility is tied to the exact GSM's processing paragraph, not to organism alone.
    atac = next(a for a in ws.assets() if a["body"]["name"] == "GSM6068778_LentiGFP1_peaks.narrowPeak" and a["blob"])
    snapshots = ws.rows("SELECT blob FROM snapshot WHERE locator LIKE ? AND outcome='available_full' ORDER BY retrieved DESC", ("%targ=gsm&acc=GSE201627&%",))
    metadata = ws.blob_path(snapshots[0]["blob"]).read_text()
    block = metadata.split("^SAMPLE = GSM6068778", 1)[1].split("^SAMPLE = ", 1)[0]
    if "rn6" not in block.lower():
        raise DawError("atac_assembly_unresolved")
    evidence_blob = snapshots[0]["blob"]
    settings = {"native_coordinates": "0-based-half-open", "interval_schema": "narrowPeak"}
    assertions = {field_name: field(ws, atac, field_name, value, block, evidence_blob, "text:" + block,
                  "reviewed native narrowPeak format contract; no coordinate relabeling") for field_name, value in settings.items()}
    assertions["reference"] = field(ws, atac, "reference", references["rn6"], block, evidence_blob, "text:" + block, "GSM6068778 source explicitly identifies rn6")
    accepted.append(accept(ws, Curation(asset_revision=atac["id"], kind="interval", settings=settings, assertions=assertions,
        reference=references["rn6"], limitations=["ATAC accessibility calls in rat Schwann context; not transcription-factor binding"])))
    for assembly, named in domains.items():
        for gene, domain in named.items():
            request = Query(question_id=f"{gene} · {assembly} annotated gene-span inspection", operator="signal.interval_summary" if assembly == "hg38" else "interval.overlap",
                region=Region.model_validate(domain["region"]), scope=[ws.bundle_for(bw), ws.bundle_for(atac)])
            result = query(ws, request)
            outcomes.append({**result, **render_report(ws, result["run"])})
            print(assembly, gene, result["measurements"], result["run"], flush=True)
    write_json("docs/receipts/pilot-genomic-results.json", {"references": references, "domains": domains,
              "curations": accepted, "queries": outcomes, "threshold_validation": threshold_blob})


if __name__ == "__main__":
    workspace = Workspace("workspaces/pilot")
    with workspace.writer():
        run(workspace)
    workspace.close()
