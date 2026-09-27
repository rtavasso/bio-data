"""A version-pinned repository table queried literally, without guessing normalization."""
import csv

import pyarrow.parquet as pq

from daw.catalog import Workspace
from daw.curation import accept, add_assertion
from daw.models import AssertionInput, Curation, Evidence, Query
from daw.query import query, render_report
from daw.util import DawError, write_json


ws = Workspace("workspaces/pilot")
with ws.writer():
    asset = next(a for a in ws.assets() if a["body"]["name"] == "FPKM-NF2-VS-71.txt" and a["blob"])
    if asset["blob"] != "ea7d3984c78f7e75760c1bf222d6a84ea304a9781da966cb941225ff6e28f094":
        raise DawError("recipe_input_changed")
    with ws.blob_path(asset["blob"]).open() as stream:
        header_text = stream.readline().rstrip("\r\n")
    header = next(csv.reader([header_text], delimiter="\t"))
    settings = {"namespace": "literal_source_gene_name", "selection": "unknown", "units": "source_value_unspecified",
                "feature_column": 1, "columns": {name: i for i, name in enumerate(header[1:], 2)}}
    assertions = {name: add_assertion(ws, AssertionInput(subject=asset["resource_id"], field=name, value=value,
        raw_value=header_text, evidence=Evidence(blob=asset["blob"], locator="lines:1-1",
        method="literal header mapping; unspecified units/completeness do not assert biological semantics")))
        for name, value in settings.items() if name in {"namespace", "selection", "units"}}
    accepted = accept(ws, Curation(asset_revision=asset["id"], kind="table", settings=settings, assertions=assertions,
        limitations=["Filename labels FPKM; no source-backed transformation or donor mapping has been established",
                     "Tumor bulk mixture; not pure Schwann cells or an independent normal-Schwann replication",
                     "No re-normalization, pooled effect, or promoter interpretation is enabled"]))
    outputs = []
    for feature in ("PMP22", "SOX10"):
        result = query(ws, Query(question_id=f"{feature} · repository-deposited tumor table, literal values",
            operator="table.feature_lookup", feature=feature, scope=[ws.bundle_for(asset)]))
        rows = pq.read_table(ws.blob_path(result["artifacts"]["measurements.parquet"])).to_pylist()
        with ws.blob_path(asset["blob"]).open() as stream:
            truth = [row for row in csv.reader(stream, delimiter="\t") if row[0] == feature]
        expected = dict(zip(header[1:], map(float, truth[0][1:]), strict=True)) if len(truth) == 1 else {}
        if len(rows) != len(header) - 1 or {r["field"]: r["value"] for r in rows} != expected:
            raise DawError("repository_table_truth_mismatch")
        outputs.append({**result, **render_report(ws, result["run"]), "direct_source_row_match": True})
        print(feature, result["measurements"], result["run"], flush=True)
    write_json("docs/receipts/repository-table-results.json", {"curation": accepted, "queries": outputs,
        "source_blob": asset["blob"], "record_version": "21324866", "units_status": "unspecified"})
ws.close()
