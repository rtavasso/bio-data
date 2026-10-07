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
    (root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0.0\n")
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


def test_registration_path_error_explains_recovery_without_losing_dependency(ws, tmp_path):
    runner = CliRunner()
    prefix = ["-w", str(ws.root)]
    source = tmp_path / "context.json"
    source.write_text('{"synthetic": true}\n')
    output = tmp_path / "result.json"
    output.write_bytes(source.read_bytes())
    code = tmp_path / "copy_context.py"
    code.write_text("import shutil, sys\nshutil.copyfile(sys.argv[1], sys.argv[2])\n")
    args = prefix + ["register", str(output), "--code", str(code), "--input"]
    invalid = runner.invoke(app, args + [str(source)])
    assert invalid.exit_code != 0 and isinstance(invalid.exception, DawError)
    assert invalid.exception.reason == "invalid_blob_hash"
    assert str(source) in invalid.exception.detail and "bio object add" in invalid.exception.detail
    assert not ws.rows("SELECT * FROM artifact")
    preserved = runner.invoke(app, prefix + ["object", "add", str(source)])
    assert preserved.exit_code == 0, preserved.output
    blob = json.loads(preserved.output)["blob"]
    registered = runner.invoke(app, args + [blob])
    assert registered.exit_code == 0, registered.output
    shown = runner.invoke(app, prefix + ["artifact", "show", json.loads(registered.output)["artifact"]])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["manifest"]["derivation"]["inputs"][0]["blob"] == blob


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


def test_gap_withdrawal_and_legacy_correction_do_not_rank_false_failures(ws):
    q = create_question(ws, "Audit browser provenance")["question"]
    other = create_question(ws, "Different question")["question"]
    bad = record_event(ws, q, "retrieval_gap", gap_payload())
    original = ws.blob_path(bad["body_blob"]).read_bytes()
    record_event(ws, q, "retrieval_gap_correction", {
        "supersedes_event": bad["id"], "correction": "Withdrawn: browser calls were never executed."})
    report = report_gaps(ws, question=q)
    assert report["matching_events"] == 0 and report["corrected_count"] == 1
    assert report["corrections_requiring_review"][0]["event"] == bad["id"]
    with pytest.raises(DawError, match="invalid_gap_withdrawal_target"):
        record_event(ws, other, "retrieval_gap_withdrawal", {"event": bad["id"], "reason": "Wrong question"})
    withdrawal = record_event(ws, q, "retrieval_gap_withdrawal", {
        "event": bad["id"], "reason": "No actual browser tool calls in captured transcript"})
    report = report_gaps(ws, question=q, since=bad["created"])
    assert report["matching_events"] == 0 and report["withdrawn_count"] == 1
    assert report["corrected_count"] == 0
    assert report["withdrawn_events"][0]["withdrawals"][0]["event"] == withdrawal["id"]
    assert ws.blob_path(bad["body_blob"]).read_bytes() == original
    record_event(ws, q, "retrieval_gap", gap_payload(gap_key="actual HTTP 403"))
    assert report_gaps(ws)["matching_events"] == 1


def test_gap_cli_preserves_receipt_and_explicit_withdrawal(ws, tmp_path):
    q = create_question(ws, "Actual retrieval")["question"]
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"url":"https://example.test/source","status":403}')
    runner = CliRunner()
    prefix = ["--workspace", str(ws.root), "work"]
    result = runner.invoke(app, prefix + ["gap", q, "--need", "Source", "--failed", "HTTP 403",
                                        "--evidence", str(receipt)])
    assert result.exit_code == 0, result.output
    gap = json.loads(result.output)
    payload = read_json(ws.blob_path(gap["body_blob"]))
    assert ws.blob_path(payload["evidence_blob"]).read_bytes() == receipt.read_bytes()
    result = runner.invoke(app, prefix + ["gap-withdraw", q, gap["id"], "--reason", "Fixture report withdrawn"])
    assert result.exit_code == 0, result.output
    assert report_gaps(ws)["withdrawn_count"] == 1


def test_research_instructions_do_not_require_historical_specs():
    text = Path("AGENTS.md").read_text()
    assert "bio --help" in text and len(text.split()) < 400
    assert not any(name in text for name in ("BUILD_SPEC.md", "v2_SPEC.md", "v3_SPEC.md"))


def _article_with_paragraphs(count):
    paragraphs = "".join(f"<p>Paragraph {i} reports knockdown counts in Schwann cells.</p>" for i in range(count))
    return (b'<?xml version="1.0" encoding="UTF-8"?><article><front><article-meta><title-group><article-title>'
            b"A long knockdown article</article-title></title-group></article-meta></front><body><sec><title>Results"
            b"</title>" + paragraphs.encode() + b"</sec></body></article>")


def test_data_search_leaves_out_article_paragraphs_unless_asked(ws):
    """Spec v2 C9: a 200-paragraph article cannot crowd dataset hits; paragraph search is its own flag."""
    import httpx

    from daw.adapters import Sources
    from daw.embeddings import embed_documents
    from daw.search import index_document, search
    from daw.transport import Transport
    with ws.writer():
        for n in range(3):
            body = ws.put_json({"dataset": n})
            index_document(ws, key=f"dataset:{n}", family="data", subject=f"dataset_{n}", record_id=body,
                           title=f"Dataset {n}: knockdown counts per sample", summary="Per-sample counts.",
                           body_blob=body, provider="geo", format="tsv", level=2)
        transport = Transport(ws, http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=_article_with_paragraphs(200))), sleep=lambda _: None)
        fetched = Sources(ws, transport).fulltext("PMC4242")
        assert fetched["paragraphs"] == 200
        embed_documents(ws)
    runner = CliRunner()
    prefix = ["-w", str(ws.root)]

    def run(*args):
        result = runner.invoke(app, prefix + list(args))
        assert result.exit_code == 0, result.output
        return json.loads(result.output)
    default = run("data", "search", "--text", "knockdown")
    assert default["total"] == 4 and {i["format"] for i in default["items"]} == {"tsv", "jats"}
    assert run("search", "--text", "knockdown")["total"] == 4
    assert run("data", "search", "--text", "knockdown", "--limit", "100", "--offset", "3")["total"] == 4
    paragraphs = run("data", "search", "--text", "knockdown", "--paragraphs", "--limit", "100")
    assert paragraphs["total"] == 200 and {i["format"] for i in paragraphs["items"]} == {"jats-paragraph"}
    assert paragraphs["items"][0]["record_id"].startswith("sec[1]/p[")
    assert run("data", "search", "--text", "knockdown", "--format", "jats-paragraph")["total"] == 200
    # An empty query lists the inventory: still no paragraphs unless asked.
    assert run("data", "search")["total"] == 4
    vector = run("search", "--vector-text", "knockdown counts", "--family", "data", "--limit", "100")
    assert vector["total"] == 4 and "jats-paragraph" not in {i["format"] for i in vector["items"]}
    assert run("search", "--vector-text", "knockdown counts", "--paragraphs")["total"] == 200
    with pytest.raises(DawError, match="conflicting_search_format"):
        search(ws, "knockdown", paragraphs=True, format="tsv")
