"""Real-data v2 retrieval/reuse pilot. Requires preserved v1 pilot objects.

Run with DAW_LIVE=1 for the bounded public-search baseline. Network is otherwise
disabled; a previously recorded baseline can be replayed. No downloaded code runs.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pyarrow.parquet as pq

from daw.adapters import Sources
from daw.artifacts import attach_artifact, derivation_key, find_derivation, provenance, register_artifact
from daw.catalog import Workspace, restore_check
from daw.indexer import create_job, index_status, run_job
from daw.models import Discovery, Evidence
from daw.profiles import add_profile
from daw.search import search
from daw.substrate_models import ArtifactRegistration, Derivation, IndexPlan, ObjectInput, Profile
from daw.util import canonical, environment_identity, file_hash, now, read_json, write_json
from daw.work import create_question, record_event, sync_work

COUNTS = "b3d15fe88a6a680290cb57a382ac93c9f5451966d5d20b58bfa2994b0ddcb580"
FEATURES = ("Pmp22", "Sox10", "PMP22", "SOX10", "MS4A1")

# These are ordinary, locally authored scientific scripts, copied into questions.
PREPARE = '''import csv, sys
import pyarrow as pa
import pyarrow.parquet as pq
with open(sys.argv[1], newline="") as stream:
    reader = csv.reader(stream, delimiter="\\t")
    names = next(reader)
    rows = list(reader)
assert len(set(names)) == len(names), "duplicate headers require explicit handling"
assert all(len(row) == len(names) for row in rows), "ragged source rows"
columns = {name: pa.array([row[i] for row in rows], type=pa.string()) for i, name in enumerate(names)}
columns["__source_row"] = pa.array(range(2, len(rows) + 2), type=pa.int64())
pq.write_table(pa.table(columns), sys.argv[2], compression="zstd")
'''

LOOKUP = '''import json, sys
import pyarrow.compute as pc
import pyarrow.parquet as pq
table = pq.read_table(sys.argv[1])
feature = sys.argv[3]
rows = table.filter(pc.equal(table["#Geneid"], feature)).to_pylist()
result = {"feature": feature, "rows": rows, "semantics": "literal source cell strings; no normalization",
          "absence_policy": "empty lookup is unresolved, never a null biological effect"}
with open(sys.argv[2], "w") as stream:
    json.dump(result, stream, sort_keys=True)
'''


def bounded_job(ws, level):
    job = create_job(ws, IndexPlan(level=level, max_tasks=100, max_seconds=300))
    attempts = []
    for _ in range(20):
        result = run_job(ws, job["id"])
        attempts.append({k: v for k, v in result.items() if k != "tasks"})
        print(canonical({"progress": "index", "level": level, **attempts[-1]}).decode(), flush=True)
        if result["state"] != "pending":
            return {"job": job["id"], "attempts": attempts, "status": index_status(ws, job["id"], limit=100)}
    raise RuntimeError("pilot's bounded indexing passes exhausted; frontier retained")


def public_baseline(ws, destination):
    if destination.exists():
        return read_json(destination)
    if os.environ.get("DAW_LIVE") != "1":
        return {"state": "not_run", "reason": "Set DAW_LIVE=1 to record the bounded public-search baseline"}
    source = Sources(ws)
    outputs = []
    try:
        for gene in ("PMP22", "SOX10"):
            request = Discovery(provider="europepmc", query=gene + " AND Schwann", max_pages=1, page_size=20)
            result = source.discover(request)
            snapshots = [ws.one("SELECT * FROM snapshot WHERE id=?", (p["source_snapshot_id"],)) for p in result["pages"]]
            hits = [{"id": r, "body": json.loads(ws.one("SELECT body FROM resource WHERE id=?", (r,))["body"])} for r in result["resources"]]
            outputs.append({"gene": gene, "run": result["run"], "request": request.model_dump(),
                "exhausted": result["exhausted"], "warnings": result["warnings"], "snapshots": snapshots,
                "hits": [{"id": h["id"], "pmcid": h["body"].get("pmcid"), "title": h["body"].get("title")} for h in hits],
                "gse201623_mentioned_in_returned_metadata": any("GSE201623" in canonical(h["body"]).decode() for h in hits),
                "source_objects": [s["blob"] for s in snapshots]})
    finally:
        source.http.close()
    receipt = {"created": now(), "state": "recorded", "queries": outputs,
        "limitations": ["Two bounded Europe PMC searches, not an exhaustive web or agent benchmark",
            "Literature records and data representations are different retrieval units",
            "Absence from these pages is not absence from public literature or data"]}
    write_json(destination, receipt)
    return receipt


def run_script(ws, question, script, args):
    command = [sys.executable, str(script), *map(str, args)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    record_event(ws, question, "command", {"argv": command, "exit_code": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr, "code_blob": ws.put_file(script, "code")})
    if result.returncode:
        raise RuntimeError(result.stderr)


def questions(ws, asset, source_profile, destination):
    if destination.exists():
        prior = read_json(destination)
        # A recorded pilot remains reproducible from its pinned scripts/environment.
        assert ws.one("SELECT id FROM artifact WHERE id=?", (prior["prepared_artifact"]["artifact"],))
        return prior
    q1 = create_question(ws, "What source values are available for Pmp22 in GSE201623?")
    q2 = create_question(ws, "Can Sox10 use the same source-preserving preparation?")
    first, second = Path(q1["path"]), Path(q2["path"])
    prepare = first / "scripts/prepare.py"
    prepare.write_text(PREPARE)
    output = first / "outputs/prepared.parquet"
    run_script(ws, q1["question"], prepare, [ws.blob_path(COUNTS), output])
    env = environment_identity()
    derivation = Derivation(inputs=[ObjectInput(blob=COUNTS, role="source_table", source_identity=asset["id"],
        selector={"representation": "entire supplied table"})], code=[ws.put_file(prepare, "code")],
        parameters={"cell_representation": "string", "source_rows": "1-based including header", "normalization": "none"},
        references=[], environment=env, command=["python", "{code}", "{source_table}", "{output}"])
    registration = ArtifactRegistration(title="GSE201623 rat Schwann source-preserving expression table",
        summary="All original cell strings and source rows prepared once as Parquet for arbitrary gene lookup",
        kind="parquet", output_role="prepared_table", derivation=derivation,
        limitations=["Gene-level table; no promoter-specific output", "No normalization, pooling, or donor inference"])
    prepared = register_artifact(ws, output, registration, question=q1["question"])
    reusable = find_derivation(ws, derivation, "prepared_table")
    assert reusable["state"] == "reusable"
    attached = attach_artifact(ws, q2["question"], prepared["artifact"], name="prepared.parquet")
    assert file_hash(Path(attached["copy"])) == file_hash(output)

    # Independently validate every prepared cell against Python's source TSV reader.
    with ws.blob_path(COUNTS).open(newline="") as stream:
        original = list(csv.DictReader(stream, delimiter="\t"))
    table_rows = pq.read_table(output).to_pylist()
    assert len(original) == len(table_rows)
    for row_number, (raw, stored) in enumerate(zip(original, table_rows, strict=True), 2):
        assert stored.pop("__source_row") == row_number
        assert raw == stored

    answers = []
    for question, folder, feature in ((q1, first, "Pmp22"), (q2, second, "Sox10")):
        script, values = folder / "scripts/lookup.py", folder / "outputs/values.json"
        script.write_text(LOOKUP)
        run_script(ws, question["question"], script, [folder / "outputs/prepared.parquet", values, feature])
        result = read_json(values)
        truth = [{**row, "__source_row": i} for i, row in enumerate(original, 2) if row["#Geneid"] == feature]
        assert result["rows"] == truth and len(truth) > 0
        answer = register_artifact(ws, values, ArtifactRegistration(title=f"GSE201623 {feature} source cells",
            summary="Exact source values and row locators; not an effect estimate or promoter result",
            derivation=Derivation(inputs=[ObjectInput(blob=prepared["output_blob"], source_identity=prepared["artifact"],
                selector={"#Geneid": feature})], code=[ws.put_file(script, "code")], parameters={"feature": feature},
                references=[], environment=env, command=["python", "{code}", "{prepared_table}", "{output}", feature])),
            question=question["question"])
        (folder / "LABBOOK.md").write_text(f"# {feature} in GSE201623\n\n"
            f"## Investigation\nFind literal gene-table values without using a typed platform query.\n\n"
            f"## Data and prior work\nSource asset: {asset['id']}; SHA256: {COUNTS}. "
            f"Source-backed context profile: {source_profile['profile']}. "
            f"Prepared artifact: {prepared['artifact']}. "
            + ("Prepared the entire source table once.\n\n" if feature == "Pmp22" else
               "Reused the first question's exact preparation without rerunning prepare.py.\n\n")
            + f"## Findings\n{len(truth)} matching source row(s). Output artifact: {answer['artifact']}. "
            "All prepared cells were independently compared with the original TSV.\n\n"
            "## Failed routes\nFilename/title-only discovery did not advertise the queried feature; "
            "bounded public-search results are in the pilot retrieval receipt.\n\n"
            "## Assumptions and limitations\nValues are source strings. No differential expression, "
            "normalization, donor independence, promoter usage, or causal mechanism inferred. "
            "A missing label is unresolved, not biological absence.\n\n"
            "## Open questions\nAssess design and replication before estimating effects; "
            "other assays and unacquired files need separate inspection.\n")
        snapshot = sync_work(ws, question["question"], summary=f"Recovered {feature} source cells using shared GSE201623 preparation", status="completed")
        answers.append({"question": question["question"], "path": str(folder), "snapshot": snapshot["snapshot"],
            "feature": feature, "result": result, "artifact": answer})
    assert search(ws, "Pmp22", family="work")["total"] > 0
    assert search(ws, "Schwann", family="artifact")["total"] > 0
    changed = derivation.model_copy(update={"parameters": {**derivation.parameters, "normalization": "different"}})
    assert find_derivation(ws, changed, "prepared_table")["state"] == "missing"
    receipt = {"created": now(), "source": asset["id"], "source_blob": COUNTS,
        "source_rows_verified": len(original), "source_cells_verified": sum(map(len, original)),
        "prepared_artifact": prepared, "preparation_executions": 1, "reuse_state": reusable["state"],
        "same_bytes_second_question": True, "changed_parameters_key": derivation_key(ws, changed),
        "questions": answers, "provenance": provenance(ws, prepared["artifact"], depth=4)}
    write_json(destination, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path("workspaces/v2-pilot"))
    parser.add_argument("--receipts", type=Path, default=Path("docs/v2/receipts"))
    args = parser.parse_args()
    args.receipts.mkdir(parents=True, exist_ok=True)
    if not args.workspace.exists():
        backup = read_json("docs/receipts/backup-restore.json")["backup"]["path"]
        shutil.copytree(backup, args.workspace)
    ws = Workspace.create(args.workspace)
    try:
        with ws.writer():
            baseline_path = args.receipts / "metadata-baseline.json"
            if not baseline_path.exists():
                assert not ws.rows("SELECT id FROM dataset_profile WHERE level=2"), "baseline must precede deep indexing"
                metadata = bounded_job(ws, 1)
                metadata["queries"] = {gene: search(ws, gene, family="data", limit=100) for gene in FEATURES}
                write_json(baseline_path, metadata)
            public = public_baseline(ws, args.receipts / "public-search.json")
            deep = bounded_job(ws, 2)
            deep["queries"] = {gene: search(ws, feature=gene, family="data", limit=100) for gene in FEATURES}
            deep["title_unadvertised"] = {gene: [h["subject"] for h in result["items"] if gene.casefold() not in h["title"].casefold()]
                for gene, result in deep["queries"].items()}
            write_json(args.receipts / "deep-index.json", deep)
            asset = next(a for a in ws.assets() if a["blob"] == COUNTS)
            assert any(h["subject"] == asset["id"] for h in deep["queries"]["Pmp22"]["items"])
            title = json.loads(ws.one("SELECT body FROM resource WHERE kind='study' AND native_id='GSE201623'")["body"])["fields"]["Series_title"][0]
            assert "pmp22" not in title.casefold() and "sox10" not in title.casefold()
            evidence = None
            for snap in ws.rows("SELECT blob FROM snapshot WHERE locator LIKE '%GSE201623%' AND blob IS NOT NULL"):
                try:
                    lines = ws.blob_path(snap["blob"]).read_text().splitlines()
                except UnicodeDecodeError:
                    continue
                for number, line in enumerate(lines, 1):
                    if line.startswith("!Series_title = ") and title in line:
                        evidence = Evidence(blob=snap["blob"], locator=f"lines:{number}-{number}", method="original GEO SOFT series title")
                        break
                if evidence:
                    break
            assert evidence, "source-backed profile requires original GEO metadata"
            profile = add_profile(ws, Profile(subject=asset["id"], origin="agent:v2-pilot", level=3,
                title="Rat Schwann RNA-seq under Egr2-AS perturbation",
                summary="Processed gene table with four source-labelled columns; arbitrary gene lookup is possible. Design and comparability need question-local review.",
                facts={"source_title": title, "representation": "original gene table", "sample_columns": ["LentiAS-1", "LentiAS-2", "LentiGFP-1", "LentiGFP-2"]},
                apparent_affordances=["literal gene-level source lookup", "review design for expression analysis"],
                limitations=["Not promoter-specific", "Replicate independence not established by column names"],
                evidence=[evidence, Evidence(blob=COUNTS, locator="lines:1-1", method="original source table header")]))
            reuse = questions(ws, asset, profile, args.receipts / "question-reuse.json")
            summary = {"created": now(), "workspace": str(ws.root), "catalog_version": 3,
                "inventory": index_status(ws), "source_title": title,
                "feature_hits": {k: v["total"] for k, v in deep["queries"].items()},
                "title_unadvertised_hits": {k: len(v) for k, v in deep["title_unadvertised"].items()},
                "public_baseline_state": public["state"], "questions": [q["question"] for q in reuse["questions"]],
                "prepared_artifact": reuse["prepared_artifact"]["artifact"], "source_cells_verified": reuse["source_cells_verified"],
                "new_v1_curation_required": False, "requests_during_deep_index": sum(a["requests"] for a in deep["attempts"])}
            write_json(args.receipts / "summary.json", summary)
            backup_path = args.workspace.parent / ("v2-backup-" + now().replace(":", "").replace(".", "-"))
            backup = ws.backup(backup_path)
        restored = restore_check(backup_path)
        write_json(args.receipts / "backup-restore.json", {"created": now(), "backup": backup, "restore": restored})
        assert restored["ok"]
        print(canonical(summary).decode())
    finally:
        ws.close()


if __name__ == "__main__":
    main()
