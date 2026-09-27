import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daw.bio_cli import app
from daw.gaps import report_gaps
from daw.indexer import create_job, enqueue, index_status, run_job
from daw.substrate_models import IndexPlan
from daw.util import DawError, now, read_json
from daw.work import create_question, record_event


def test_fresh_session_uses_help_and_question_tools_without_specs(tmp_path):
    runner = CliRunner()
    assert "work" in runner.invoke(app, ["--help"]).output
    root = tmp_path / "research"
    assert runner.invoke(app, ["init", str(root)]).exit_code == 0
    prefix = ["-w", str(root)]
    q = runner.invoke(app, prefix + ["work", "new", "What can distinguish two mechanisms?"])
    qid = json.loads(q.output)["question"]
    for family in ("data", "artifact", "work"):
        found = runner.invoke(app, prefix + [family, "search", "--text", "mechanisms"])
        assert found.exit_code == 0, found.output
    gap = runner.invoke(app, prefix + ["work", "gap", qid, "--need", "Cell state metadata",
        "--failed", "Only feature names are indexed", "--source-or-format", "H5AD"])
    assert gap.exit_code == 0, gap.output
    report = runner.invoke(app, prefix + ["work", "gaps"])
    assert json.loads(report.output)["groups"][0]["distinct_questions"] == 1


@pytest.mark.parametrize("legacy_state", ["pending", "deferred", "blocked", "running"])
def test_v2_semantic_tasks_cannot_block_or_be_retried_by_v3(ws, tmp_path, legacy_state):
    path = tmp_path / "table.tsv"
    path.write_text("gene\tvalue\nPMP22\t0\n")
    asset = ws.local_asset(path)
    job = create_job(ws, IndexPlan(level=3, scope=[asset["asset_revision"]]))
    tid = enqueue(ws, job["id"], "semantic", asset["asset_revision"])
    receipt = ws.put_json({"reason": "v2 semantic profile missing"})
    with ws.db:
        ws.db.execute("UPDATE index_task SET state=?,result_blob=? WHERE id=?", (legacy_state, receipt, tid))
    result = run_job(ws, job["id"], retry=True)
    assert result["state"] == "complete"
    old = ws.one("SELECT * FROM index_task WHERE id=?", (tid,))
    assert old["state"] == legacy_state and old["result_blob"] == receipt and old["attempts"] == 0
    assert index_status(ws, job["id"])["frontier"] == []
    assert not ws.rows("SELECT id FROM dataset_profile WHERE level=3")


def test_optional_semantics_do_not_hide_structural_failure(ws, tmp_path):
    path = tmp_path / "untrusted.rds"
    path.write_bytes(b"opaque object must not execute")
    asset = ws.local_asset(path)
    job = create_job(ws, IndexPlan(level=3))
    result = run_job(ws, job["id"])
    assert result["state"] == "partial"
    assert any(t["target"] == asset["asset_revision"] for t in index_status(ws, job["id"])["frontier"])


def gap_payload(**extra):
    return {"desired_information": "Schwann cell state labels", "why_current_tools_failed": "Only var labels are searchable",
        "source_or_format": "H5AD", "likely_value": "high for this question", "gap_key": "obs labels", **extra}


def test_gaps_count_questions_separately_preserve_extra_fields_and_restrict_time(ws):
    a, b = create_question(ws, "First"), create_question(ws, "Second")
    before = now()
    events = [record_event(ws, q, "retrieval_gap", gap_payload(custom_context={"donor": "unknown"}))
              for q in (a["question"], a["question"], b["question"])]
    report = report_gaps(ws, since=before)
    group = report["groups"][0]
    assert group["observations"] == 3 and group["distinct_questions"] == 2
    assert read_json(ws.blob_path(events[0]["body_blob"]))["custom_context"] == {"donor": "unknown"}
    assert report_gaps(ws, question=b["question"])["matching_events"] == 1
    assert report_gaps(ws, since="2100-01-01T00:00:00+00:00")["matching_events"] == 0
    assert report_gaps(ws, source="xlsx")["matching_events"] == 0
    assert not report_gaps(ws, max_events=1)["scan_complete"]
    assert report["content_is_untrusted_data"]


@pytest.mark.parametrize("payload", [{}, [], {"desired_information": "need", "why_current_tools_failed": ""}])
def test_gap_minimum_fields_are_checked_before_writing(ws, payload):
    q = create_question(ws, "Question")
    with pytest.raises(DawError, match="invalid_retrieval_gap"):
        record_event(ws, q["question"], "retrieval_gap", payload)
    assert not ws.rows("SELECT * FROM work_event WHERE kind='retrieval_gap'")


def test_gap_wrong_question_and_legacy_freeform_remain_auditable(ws):
    q = create_question(ws, "Question")
    with pytest.raises(DawError, match="question_mismatch"):
        record_event(ws, q["question"], "retrieval_gap", gap_payload(question="another"))
    blob = ws.put_json({"freeform": "old v2 note"})
    with ws.db:
        ws.db.execute("INSERT INTO work_event VALUES(?,?,?,?,?)", ("old-gap", q["question"], "retrieval_gap", blob, now()))
    report = report_gaps(ws)
    assert report["unstructured_count"] == 1 and report["matching_events"] == 0
    assert report["unstructured_events"][0]["body_blob"] == blob
    with pytest.raises(DawError, match="invalid_gap_since"):
        report_gaps(ws, since="2026-01-01")


def test_research_instructions_do_not_require_historical_specs():
    text = Path("AGENTS.md").read_text()
    assert "bio --help" in text and len(text.split()) < 400
    assert not any(name in text for name in ("BUILD_SPEC.md", "v2_SPEC.md", "v3_SPEC.md"))
