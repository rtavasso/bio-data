import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from daw.curation import accept, add_assertion, capability, validate_curation
from daw.models import AssertionInput, Curation, Evidence, Query
from daw.query import query
from daw.util import DawError, read_json


def test_selected_omission_is_not_null_and_zero_is_preserved(ws, tmp_path, curated):
    path = tmp_path / "selected.tsv"
    path.write_text("gene\teffect\nPMP22\t0\nNA\t2\n")
    imported = ws.local_asset(path)
    curated(imported, settings={"feature_column": 1, "columns": {"effect": 2}, "namespace": "literal", "selection": "significant_only"})
    yes = query(ws, Query(question_id="zero", operator="table.feature_lookup", feature="PMP22", scope=[imported["bundle"]]))
    table = pq.read_table(ws.blob_path(yes["artifacts"]["measurements.parquet"])).to_pylist()
    assert table[0]["value"] == 0.0
    no = query(ws, Query(question_id="absent", operator="table.feature_lookup", feature="MISSING", scope=[imported["bundle"]]))
    coverage = pq.read_table(ws.blob_path(no["artifacts"]["coverage.parquet"])).to_pylist()
    assert coverage[0]["result_state"] == "unresolved"
    assert "no_null_effect" in coverage[0]["reason"]
    literal = query(ws, Query(question_id="literal", operator="table.feature_lookup", feature="NA", scope=[imported["bundle"]]))
    assert literal["measurements"] == 1


def test_multiple_regions_and_unexamined_sheet_coverage(ws, tmp_path, curated):
    import openpyxl
    path = tmp_path / "multi.xlsx"
    book = openpyxl.Workbook()
    book.active.title = "data"
    for row in [["gene", "v"], ["PMP22", 1], ["gene", "v"], ["PMP22", 3]]:
        book.active.append(row)
    book.create_sheet("unexamined").append(["unknown assay"])
    book.save(path)
    imported = ws.local_asset(path)
    from daw.inspectors import inspect_asset
    inspect_asset(ws, imported["asset_revision"], isolated=False)
    curated(imported, selector={"sheet": "data", "start_row": 2, "end_row": 2})
    curated(imported, selector={"sheet": "data", "start_row": 4, "end_row": 4})
    output = query(ws, Query(question_id="regions", operator="table.feature_lookup", feature="PMP22"))
    assert output["measurements"] == 2 and output["candidates"] == 3
    cov = pq.read_table(ws.blob_path(output["artifacts"]["coverage.parquet"])).to_pylist()
    assert sum(c["result_state"] == "pending" for c in cov) == 1


def test_corrected_mapping_invalidates_run_without_mutating_old(ws, tmp_path, curated):
    path = tmp_path / "a.tsv"
    path.write_text("gene\ta\tb\nPMP22\t1\t2\n")
    imported = ws.local_asset(path)
    proposal, first = curated(imported)
    request = Query(question_id="mapping", operator="table.feature_lookup", feature="PMP22")
    original = query(ws, request)
    cached = query(ws, request)
    assert cached["reused_from"] == original["run"]
    updated = proposal.model_copy(deep=True)
    updated.settings["columns"] = {"effect": 3}
    updated.supersedes = first["digest"]
    second = accept(ws, updated)
    result = query(ws, request)
    assert result["work_key"] != original["work_key"]
    assert pq.read_table(ws.blob_path(result["artifacts"]["measurements.parquet"]))["value"].to_pylist() == [2.0]
    assert pq.read_table(ws.blob_path(original["artifacts"]["measurements.parquet"]))["value"].to_pylist() == [1.0]
    assert second["digest"] != first["digest"]
    assert ws.one("SELECT stale FROM run WHERE id=?", (original["run"],))["stale"] == 1


def test_assertions_must_match_preserved_evidence(ws, tmp_path):
    path = tmp_path / "a.tsv"
    path.write_text("gene\tx\nA\t1")
    imported = ws.local_asset(path)
    subject = ws.asset(imported["asset_revision"])["resource_id"]
    blob = ws.put_json({"units": "log-normalized"})
    with pytest.raises(DawError, match="evidence_value_mismatch"):
        add_assertion(ws, AssertionInput(subject=subject, field="units", raw_value="counts", value="counts",
                                        evidence=Evidence(blob=blob, locator="/units")))


def test_conflicting_evidence_and_self_approval_rejected(ws, tmp_path, curated):
    path = tmp_path / "a.tsv"
    path.write_text("gene\tx\nA\t1\n")
    imported = ws.local_asset(path)
    proposal, _ = curated(imported)
    body = ws.put_json({"namespace": "conflicting"})
    add_assertion(ws, AssertionInput(subject=ws.asset(imported["asset_revision"])["resource_id"], field="namespace",
        raw_value="conflicting", value="conflicting", evidence=Evidence(blob=body, locator="/namespace")))
    assert "unresolved_conflict:namespace" in validate_curation(ws, proposal)["errors"]
    with pytest.raises(ValidationError):
        Curation.model_validate({**proposal.model_dump(), "approved": True})


def test_promoter_and_direction_gates(ws, tmp_path, curated):
    path = tmp_path / "a.tsv"
    path.write_text("gene\tx\nA\t1\n")
    proposal, _ = curated(ws.local_asset(path))
    assert capability(proposal, "promoter.tss_summary")["status"] == "not_supported"
    assert capability(proposal, "contrast.published_lookup")["status"] == "blocked"


def test_no_unrestricted_sql_in_query_contract():
    with pytest.raises(ValidationError):
        Query.model_validate({"question_id": "attack", "operator": "table.feature_lookup", "feature": "X", "sql": "read_csv('/etc/passwd')"})


def test_html_injection_escaped(ws, tmp_path, curated):
    path = tmp_path / "a.tsv"
    path.write_text("gene\tx\nA\t<script>alert(1)</script>\n")
    curated(ws.local_asset(path))
    result = query(ws, Query(question_id="<script>alert(2)</script>", operator="table.feature_lookup", feature="A"))
    html = ws.blob_path(result["artifacts"]["report.html"]).read_text()
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(2)" in html
    assert "http://" not in html and "https://" not in html
    assert read_json(ws.blob_path(result["artifacts"]["validation.json"]))["coverage_complete_for_frozen_candidate_set"]


def test_conflict_review_expires_when_new_evidence_arrives(ws, tmp_path, curated):
    from daw.curation import review_conflict
    path = tmp_path / "a.tsv"
    path.write_text("gene\tx\nA\t1\n")
    imported = ws.local_asset(path)
    proposal, _ = curated(imported)
    subject = ws.asset(imported["asset_revision"])["resource_id"]
    blob = ws.put_json({"namespace": "alternative"})
    evidence = Evidence(blob=blob, locator="/namespace")
    alternative = add_assertion(ws, AssertionInput(subject=subject, field="namespace", raw_value="alternative",
        value="alternative", evidence=evidence))
    selected = proposal.assertions["namespace"]
    assert "unresolved_conflict:namespace" in validate_curation(ws, proposal)["errors"]
    review_conflict(ws, {"reviewer": "fixture operator", "rationale": "source identifier header reviewed",
        "selected_assertion": selected, "considered_assertions": [selected, alternative], "evidence": [evidence.model_dump()]})
    assert "unresolved_conflict:namespace" not in validate_curation(ws, proposal)["errors"]
    third = ws.put_json({"namespace": "new evidence"})
    add_assertion(ws, AssertionInput(subject=subject, field="namespace", raw_value="new evidence", value="new evidence",
        evidence=Evidence(blob=third, locator="/namespace")))
    assert "unresolved_conflict:namespace" in validate_curation(ws, proposal)["errors"]
