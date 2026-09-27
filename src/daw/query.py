"""Frozen candidate plans, typed extraction packages, and complete coverage ledgers."""
import shutil
import os
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from daw.curation import capability, unresolved_conflict
from daw.models import Curation, Query
from daw.util import DawError, canonical, digest, environment_identity, file_hash, read_json, write_json

MEASUREMENT_SCHEMA = pa.schema([
    ("measurement_id", pa.string()), ("context_id", pa.string()), ("asset_revision", pa.string()),
    ("feature", pa.string()), ("field", pa.string()), ("value", pa.float64()), ("text", pa.string()),
    ("locator", pa.string()), ("criterion", pa.string()), ("details_json", pa.string()),
])
CONTEXT_SCHEMA = pa.schema([
    ("context_id", pa.string()), ("asset_revision", pa.string()), ("source_blob", pa.string()),
    ("curation_digest", pa.string()), ("operator", pa.string()), ("units", pa.string()),
    ("bundle_id", pa.string()), ("source_experiment_id", pa.string()), ("source_metadata_json", pa.string()),
    ("selector_json", pa.string()), ("settings_json", pa.string()), ("sample_map_json", pa.string()),
])
COVERAGE_SCHEMA = pa.schema([
    ("candidate_id", pa.string()), ("asset_revision", pa.string()), ("name", pa.string()),
    ("selector_json", pa.string()), ("acquisition", pa.string()), ("inspection", pa.string()),
    ("capability", pa.string()), ("result_state", pa.string()), ("reason", pa.string()),
    ("measurements", pa.int64()),
])


def execute_operator(ws, asset, curation, request):
    """One bounded scientific worker, immutable inputs, no catalog connection."""
    hashes = {asset["blob"]}
    if curation.reference:
        hashes.add(curation.reference)
    for key in ("feature_ids", "cell_ids"):
        if key in curation.settings:
            hashes.add(curation.settings[key])
    job = ws.root / "staging" / ("query-" + uuid.uuid4().hex + ".json")
    output = job.with_suffix(".out.json")
    write_json(job, {"action": "operator", "asset": asset, "curation": curation.model_dump(),
                    "request": request.model_dump(), "budgets": ws.budgets.model_dump(),
                    "blobs": {sha: str(ws.blob_path(sha)) for sha in hashes}})
    try:
        proc = subprocess.run([sys.executable, "-m", "daw.worker", str(job), str(output)], capture_output=True,
            timeout=ws.budgets.worker_seconds,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                 "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
        if not output.exists():
            raise DawError("worker_failed", f"exit code {proc.returncode}")
        result = read_json(output)
        if "error" in result:
            raise DawError(result["error"], result.get("detail", ""))
        return result["rows"], result["state"], result["reason"]
    except subprocess.TimeoutExpired as e:
        raise DawError("over_budget", "scientific worker time budget") from e
    finally:
        job.unlink(missing_ok=True)
        output.unlink(missing_ok=True)


def plan_query(ws, request: Query):
    candidates = []
    assets = ws.assets(request.scope)
    # Explicit immutable revisions remain addressable after refresh.
    for selected in request.scope:
        if ws.one("SELECT id FROM asset_revision WHERE id=?", (selected,)) and not any(a["id"] == selected for a in assets):
            assets.append(ws.asset(selected))
    for asset in assets:
        inspection = ws.one("SELECT * FROM inspection WHERE asset_revision=? ORDER BY created DESC LIMIT 1", (asset["id"],))
        curations = ws.rows("SELECT * FROM current_curation WHERE asset_revision=? ORDER BY selector", (asset["id"],))
        scopes = [(read_json(ws.blob_path(c["digest"])), c["digest"]) for c in curations]
        if inspection:
            structure = read_json(ws.blob_path(inspection["blob"]))
            covered_sheets = {c[0]["selector"].get("sheet") for c in scopes}
            for sheet in structure.get("sheets", []):
                if sheet["name"] not in covered_sheets:
                    scopes.append(({"selector": {"sheet": sheet["name"]}}, None))
        if not scopes:
            scopes = [({"selector": {}}, None)]
        for body, curation_hash in scopes:
            curation = Curation.model_validate(body) if curation_hash else None
            decision = capability(curation, request.operator, asset)
            if curation:
                conflicts = [field for field, selected in curation.assertions.items()
                             if unresolved_conflict(ws, asset["resource_id"], field, selected, curation.selector)]
                if conflicts:
                    decision = {**decision, "status": "blocked", "reasons": ["unresolved_conflict:" + f for f in conflicts]}
            if asset["access"] != "available_full":
                decision = {**decision, "status": "pending" if asset["access"] in {"listed", "not_attempted"} else "blocked",
                            "reasons": ["acquisition:" + asset["access"]]}
            if inspection and inspection["status"] in {"unsafe_to_inspect", "malformed"}:
                decision = {**decision, "status": "blocked", "reasons": ["inspection:" + inspection["status"]]}
            if request.region and curation and curation.reference != request.region.reference:
                decision = {**decision, "status": "blocked", "reasons": ["incompatible_native_reference"]}
            candidates.append({"candidate_id": digest([asset["id"], body["selector"], curation_hash]),
                               "asset_revision": asset["id"], "source_blob": asset["blob"],
                               "name": asset["body"]["name"], "selector": body["selector"],
                               "curation": curation_hash, "acquisition": asset["access"],
                               "inspection": inspection["status"] if inspection else "not_inspected", "decision": decision})
    return {"request": request.model_dump(), "candidates": candidates,
            "candidate_set_digest": digest(candidates), "denominator": len(candidates),
            "counts": dict(Counter(c["decision"]["status"] for c in candidates)),
            "scope": "frozen listed asset revisions and inventoried workbook sheets within requested local catalog scope",
            "limitations": ["coverage does not establish exhaustion of all public evidence",
                            "measurements remain stratified; no pooling across experiments or units"]}


def query(ws, request: Query):
    plan = plan_query(ws, request)
    environment = environment_identity()
    inputs = {"request": request.model_dump(), "plan": plan, "environment": environment, "budgets": ws.budgets.model_dump(),
              "references": sorted({request.region.reference} if request.region else set())}
    run, key = ws.start_run("query", inputs)
    earlier = ws.one("SELECT * FROM run WHERE work_key=? AND state='succeeded' AND stale=0 ORDER BY created DESC LIMIT 1", (key,))
    if earlier:
        output = read_json(ws.blob_path(earlier["output_blob"]))
        if all(file_hash(ws.blob_path(sha)) == sha for sha in output["artifacts"].values()):
            output = {**output, "run": run, "reused_from": earlier["id"]}
            ws.finish_run(run, output)
            with ws.db:
                ws.db.execute("INSERT INTO run_dependency SELECT ?, identity FROM run_dependency WHERE run_id=?", (run, earlier["id"]))
            render_report(ws, run)
            return output
    measurements, contexts, coverage = [], [], []
    try:
        for candidate in plan["candidates"]:
            cid, aid = candidate["candidate_id"], candidate["asset_revision"]
            decision = candidate["decision"]
            state = "pending" if decision["status"] == "pending" else "unresolved"
            reason = "; ".join(decision["reasons"])
            rows = []
            with ws.db:
                for identity in (aid, candidate["curation"]):
                    if identity:
                        ws.db.execute("INSERT OR IGNORE INTO run_dependency VALUES(?,?)", (run, identity))
            if decision["status"] in {"ready", "ready_with_limits"}:
                asset = ws.asset(aid)
                curation = Curation.model_validate(read_json(ws.blob_path(candidate["curation"])))
                try:
                    if file_hash(ws.blob_path(asset["blob"])) != asset["blob"]:
                        raise DawError("integrity_failed", "input bytes changed")
                    rows, state, reason = execute_operator(ws, asset, curation, request)
                    if len(rows) + len(measurements) > request.max_measurements:
                        raise DawError("over_budget", "measurement row budget; extraction not accepted")
                    context = {"context_id": cid, "asset_revision": aid, "source_blob": asset["blob"],
                               "curation_digest": candidate["curation"], "operator": request.operator,
                               "units": str(curation.settings.get("units", "unspecified_literal_lookup")),
                               "bundle_id": ws.bundle_for(asset),
                               "source_experiment_id": asset["body"].get("metadata", {}).get("experiment"),
                               "source_metadata_json": canonical(asset["body"].get("metadata", {})).decode(),
                               "selector_json": canonical(curation.selector).decode(),
                               "settings_json": canonical(curation.settings).decode(),
                               "sample_map_json": canonical(curation.sample_map).decode()}
                    contexts.append(context)
                    for i, row in enumerate(rows):
                        keys = {f.name for f in MEASUREMENT_SCHEMA}
                        base = {k: v for k, v in row.items() if k in keys}
                        base.update(measurement_id=digest([cid, request.model_dump(), i, row]), context_id=cid, asset_revision=aid,
                                    details_json=canonical({k: v for k, v in row.items() if k not in keys}).decode())
                        measurements.append(base)
                except (DawError, ImportError, ValueError, KeyError, OSError) as e:
                    rows, state, reason = [], "unresolved", str(e)
            coverage.append({"candidate_id": cid, "asset_revision": aid, "name": candidate["name"],
                             "selector_json": canonical(candidate["selector"]).decode(),
                             "acquisition": candidate["acquisition"], "inspection": candidate["inspection"],
                             "capability": decision["status"], "result_state": state, "reason": reason,
                             "measurements": len(rows)})
        directory = ws.root / "runs" / run
        provenance = {"inputs": inputs, "source_snapshots": sorted({ws.asset(c["asset_revision"])["snapshot_id"]
                      for c in plan["candidates"] if ws.asset(c["asset_revision"])["snapshot_id"]}),
                      "lineage": [{"asset_revision": c["asset_revision"], "blob": c["source_blob"],
                                   "curation": c["curation"], "selector": c["selector"]} for c in plan["candidates"]]}
        validation = {"coverage_complete_for_frozen_candidate_set": len(coverage) == len(plan["candidates"]),
                      "measurement_ids_unique": len({m["measurement_id"] for m in measurements}) == len(measurements),
                      "all_measurements_have_context": {m["context_id"] for m in measurements} <= {c["context_id"] for c in contexts},
                      "unrestricted_sql": False, "implicit_cross_study_pooling": False,
                      "result_counts": dict(Counter(c["result_state"] for c in coverage))}
        artifacts = {}
        for name, value in (("request.json", request.model_dump()), ("plan.json", plan),
                            ("provenance.json", provenance), ("validation.json", validation)):
            write_json(directory / name, value)
            artifacts[name] = ws.put_file(directory / name, "derived")
        for name, rows, schema in (("measurements.parquet", measurements, MEASUREMENT_SCHEMA),
                                   ("measurement_context.parquet", contexts, CONTEXT_SCHEMA), ("coverage.parquet", coverage, COVERAGE_SCHEMA)):
            pq.write_table(pa.Table.from_pylist(rows, schema=schema), directory / name, compression="zstd")
            artifacts[name] = ws.put_file(directory / name, "derived")
        output = {"run": run, "work_key": key, "artifacts": artifacts, "measurements": len(measurements),
                  "candidates": len(coverage), "result_counts": validation["result_counts"],
                  "warnings": ["Some candidates remain unresolved or pending"] if any(c["result_state"] in {"pending", "unresolved"} for c in coverage) else []}
        # HTML is derived from the same records and accepted alongside the package.
        from daw.reports import html_report
        report = html_report(run, request.model_dump(), plan, measurements, coverage, validation, contexts)
        (directory / "report.html").write_text(report)
        artifacts["report.html"] = ws.put_file(directory / "report.html", "derived")
        ws.finish_run(run, output)
        render_report(ws, run)
        return output
    except Exception as e:
        ws.finish_run(run, {"partial_coverage": coverage, "error": type(e).__name__}, str(e))
        raise


def render_report(ws, run):
    record = ws.one("SELECT * FROM run WHERE id=?", (run,))
    if not record or not record["output_blob"]:
        raise DawError("unknown_or_unfinished_run")
    output = read_json(ws.blob_path(record["output_blob"]))
    if "artifacts" not in output:
        raise DawError("run_has_no_query_package")
    directory = ws.root / "reports" / run
    directory.mkdir(parents=True, exist_ok=True)
    for name, sha in output["artifacts"].items():
        if name not in {"request.json", "plan.json", "provenance.json", "validation.json", "measurements.parquet",
                        "measurement_context.parquet", "coverage.parquet", "report.html"}:
            raise DawError("unexpected_report_artifact")
        shutil.copyfile(ws.blob_path(sha), directory / name)
    write_json(directory / "current_status.json", {"run": run, "stale": bool(record["stale"]),
                                                    "note": "historical immutable result; check current catalog before reuse"})
    return {"run": run, "report": str(directory / "report.html"), "stale": bool(record["stale"])}


def coverage_audit(ws, scope=None):
    assets = ws.assets([scope] if scope else [])
    rows = []
    for asset in assets:
        inspection = ws.one("SELECT status FROM inspection WHERE asset_revision=? ORDER BY created DESC LIMIT 1", (asset["id"],))
        capabilities = ws.rows("SELECT name,status FROM capability WHERE asset_revision=? AND curation IN (SELECT digest FROM current_curation WHERE asset_revision=?)",
                               (asset["id"], asset["id"]))
        rows.append({"asset_revision": asset["id"], "name": asset["body"]["name"], "acquisition": asset["access"],
                     "inspection": inspection["status"] if inspection else "not_inspected", "capabilities": capabilities,
                     "license": asset["body"].get("license", "unknown")})
    return {"scope": scope or "current_local_catalog", "denominator": len(rows), "assets": rows,
            "acquisition_counts": dict(Counter(r["acquisition"] for r in rows)),
            "inspection_counts": dict(Counter(r["inspection"] for r in rows)),
            "fully_acquired": sum(r["acquisition"] == "available_full" for r in rows),
            "query_ready_assets": sum(any(c["status"].startswith("ready") for c in r["capabilities"]) for r in rows),
            "scope_is_all_public_evidence": False,
            "accounting": {"immutable_bytes": ws.one("SELECT COALESCE(sum(size),0) AS n FROM blob")["n"],
                           "source_snapshots": ws.one("SELECT count(*) AS n FROM snapshot")["n"]}}
