"""Held-out human PBMC3k descriptive expression check; not Schwann-cell evidence."""
from pathlib import Path

import anndata
import numpy as np
import pyarrow.parquet as pq

from daw.catalog import Workspace
from daw.curation import accept, add_assertion
from daw.models import AssertionInput, Curation, Evidence, Query
from daw.query import query, render_report
from daw.util import DawError, digest, file_hash, write_json


def run(ws):
    asset = next(a for a in ws.assets() if a["body"]["name"] == "pbmc3k_raw.h5ad" and a["blob"])
    if asset["blob"] != "89a96f1beaa2dd83a687666d3f19a4513ac27a2a2d12581fcd77afed7ea653a1":
        raise DawError("heldout_source_changed")
    documentation = next(a for a in ws.assets() if a["body"]["name"] == "_datasets.py" and a["blob"])
    source_text = ws.blob_path(documentation["blob"]).read_text()
    quote = "3k PBMCs from a Healthy Donor"
    if quote not in source_text:
        raise DawError("source_context_quote_changed")
    data = anndata.read_h5ad(ws.blob_path(asset["blob"]), backed="r")
    try:
        cells, features = list(map(str, data.obs_names)), list(map(str, data.var_names))
        if len(cells) != len(set(cells)) or len(features) != len(set(features)):
            raise DawError("heldout_duplicate_identifiers")
        sample_map = {cell: {"study": "10x_pbmc3k", "sample": "published_pbmc3k_library", "dataset": "pbmc3k"} for cell in cells}
        settings = {"layer": "X", "units": "source_count_value", "transform": "none_in_published_conversion",
                    "namespace": "published_gene_symbols_with_original_uniquification", "feature_presence": {"pbmc3k": features},
                    "biological_context": "human peripheral blood mononuclear cells from the published PBMC3k library"}
        mapping = {**settings, "sample_map": sample_map, "input_blob": asset["blob"], "documentation_blob": documentation["blob"],
                   "recipe_sha256": file_hash(Path(__file__)), "shape": list(data.shape),
                   "rule": "Use the unchanged X matrix, published var/obs axes, and single source library; do not infer donor identifiers or subset cells",
                   "checks": {"unique_cell_ids": True, "unique_published_feature_ids": True,
                              "source_conversion": "Scanpy pbmc3k writes direct read_10x_mtx output with gene-name uniquification; no normalization"}}
        run_id, _ = ws.start_run("study_recipe", {"source_blob": asset["blob"], "documentation_blob": documentation["blob"],
                                                 "recipe_sha256": mapping["recipe_sha256"]})
        mapping_blob = ws.put_json(mapping, "derived")
        ws.finish_run(run_id, {"mapping_blob": mapping_blob, "checks": mapping["checks"]})
        assertions = {}
        for key, value in {**settings, "sample_map": sample_map}.items():
            assertions[key] = add_assertion(ws, AssertionInput(subject=asset["resource_id"], field=key,
                value=value, raw_value=value, evidence=Evidence(blob=mapping_blob, locator="/" + key,
                method="deterministic source-axis mapping with source bytes, source conversion documentation and recipe digest")))
        proposal = Curation(asset_revision=asset["id"], kind="matrix", settings=settings, sample_map=sample_map,
            assertions=assertions, limitations=["Held-out human blood dataset, not a Schwann-cell measurement",
            "No accepted cell-to-independent-donor map or counts-analysis recipe; descriptive values only"])
        accepted = accept(ws, proposal)
        request = Query(question_id="Held-out validation · human PBMC3k MS4A1 values", operator="expression.feature_values", feature="MS4A1", scope=[asset["id"]])
        result = query(ws, request)
        rows = pq.read_table(ws.blob_path(result["artifacts"]["measurements.parquet"])).to_pylist()
        expected = np.asarray(data.X[:, features.index("MS4A1"):features.index("MS4A1") + 1].toarray()).ravel()
        observed = np.array([r["value"] for r in rows], dtype=float)
        import json
        returned_ids = [json.loads(r["details_json"])["cell"] for r in rows]
        valid = len(rows) == len(cells) and returned_ids == cells and np.array_equal(expected, observed)
        blocked = query(ws, Query(question_id="Held-out eligibility · donor pseudobulk stays blocked", operator="expression.pseudobulk_counts", feature="MS4A1", scope=[asset["id"]]))
        absent = query(ws, Query(question_id="Held-out missing feature · absence differs from sparse zero", operator="expression.feature_values", feature="DAW_MISSING_FEATURE", scope=[asset["id"]]))
        receipt = {"study": "PBMC3k", "source_blob": asset["blob"], "source_dimensions": list(data.shape),
                   "curation": accepted["digest"], "query": {**result, **render_report(ws, result["run"])},
                   "independent_vector_match": valid, "row_order_preserved": returned_ids == cells,
                   "expected_vector_digest": digest(expected.tolist()), "returned_vector_digest": digest(observed.tolist()),
                   "returned_values": len(rows), "measured_zero_values": int((expected == 0).sum()),
                   "pseudobulk_check": blocked, "missing_feature_check": absent,
                   "context_limit": "Human blood; no inference about Schwann cells or PMP22 mechanism"}
        write_json("docs/receipts/heldout-validation.json", receipt)
        if not valid:
            raise DawError("heldout_numeric_validation_failed")
        print("heldout", len(rows), "values; full vector and row order match", result["run"], flush=True)
    finally:
        data.file.close()


if __name__ == "__main__":
    workspace = Workspace("workspaces/pilot")
    with workspace.writer():
        run(workspace)
    workspace.close()
