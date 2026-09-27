import os
import shutil
import sys
from pathlib import Path

import pytest

from benchmarks.agent.capture import execute, parse_events
from benchmarks.agent.models import Case
from benchmarks.agent.report import build_report, compare
from benchmarks.agent.review import review_run, validate_review
from benchmarks.agent.runner import codex_command, prepare, run, safe_path
from daw.util import file_hash, read_json, write_json


@pytest.fixture(scope="module")
def prepared_template(tmp_path_factory):
    return prepare(output=tmp_path_factory.mktemp("agent-evals"), cases=["zero-vs-missing"], timeout=30)


@pytest.fixture
def prepared(prepared_template, tmp_path):
    return Path(shutil.copytree(prepared_template, tmp_path / "run"))


def fake_codex(path):
    path.write_text(f"#!{sys.executable}\n" + '''import json, os, sys
from pathlib import Path
if "--version" in sys.argv:
    print("fixture-codex 1.0")
    raise SystemExit(0)
from daw.catalog import Workspace
from daw.work import create_question
w = Workspace(os.environ["BIO_WORKSPACE"])
with w.writer():
    create_question(w, "Fixture agent's new question")
w.close()
events = [
    {"type":"thread.started","thread_id":"fixture-thread"},
    {"type":"item.started","item":{"id":"command-1","type":"command_execution","command":"failed fixture tool","status":"in_progress"}},
    {"type":"item.completed","item":{"id":"command-1","type":"command_execution","command":"failed fixture tool","status":"completed","exit_code":2,"aggregated_output":"fixture failure"}},
    {"type":"future.event","new_field":"retained"},
    {"type":"item.completed","item":{"id":"message-1","type":"agent_message","text":"<script>alert('source text')</script>"}},
    {"type":"turn.completed","usage":{"input_tokens":12,"cached_input_tokens":4,"output_tokens":3}}
]
for e in events:
    print(json.dumps(e), flush=True)
print("fixture stderr", file=sys.stderr)
Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text("<script>alert('source text')</script>")
''')
    path.chmod(0o755)
    return str(path)


def test_prepare_is_offline_and_does_not_award_seeded_work(prepared):
    report = build_report(prepared)
    case = report["cases"][0]
    checks = {c["id"]: c["status"] for c in case["checks"]}
    assert case["status"] == "not_run"
    assert checks["question"] == checks["notebook"] == checks["scientific_review"] == "unknown"
    assert checks["preserved_inputs"] == "pass"
    assert (prepared / "report.html").is_file()
    prompt = (prepared / "cases/zero-vs-missing/prompt.txt").read_text()
    assert "review_focus" not in prompt and "source value of 5" not in prompt


def test_stock_cli_capture_records_failure_evidence_without_conflating_completion(prepared, tmp_path, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    executable = fake_codex(tmp_path / "fake codex")
    run(prepared, executable)
    case = read_json(prepared / "report.json")["cases"][0]
    assert case["status"] == "complete"
    assert case["usage"] == {"input_tokens": 12, "cached_input_tokens": 4, "output_tokens": 3, "reasoning_output_tokens": None}
    assert case["tool_counts"]["command_execution"] == 1
    assert len(case["failed_commands"]) == 1
    checks = {c["id"]: c["status"] for c in case["checks"]}
    assert checks["question"] == "pass" and checks["notebook"] == "fail"
    assert checks["scientific_review"] == "unknown"
    folder = prepared / "cases/zero-vs-missing"
    assert '"type": "future.event"' in (folder / "events.jsonl").read_text()
    assert "fixture stderr" in (folder / "stderr.log").read_text()
    rendered = (folder / "report.html").read_text()
    assert "<script>alert('source text')</script>" not in rendered
    assert "&lt;script&gt;" in rendered
    before = file_hash(folder / "events.jsonl")
    with pytest.raises(ValueError, match="prepared run"):
        run(prepared, executable)
    assert file_hash(folder / "events.jsonl") == before


def test_no_model_process_without_explicit_live_opt_in(prepared, monkeypatch):
    monkeypatch.delenv("DAW_LIVE", raising=False)
    with pytest.raises(ValueError, match="DAW_LIVE"):
        run(prepared, "does-not-exist")
    assert not (prepared / "cases/zero-vs-missing/execution.json").exists()


def test_changed_prepared_source_cannot_launch_under_old_fingerprint(prepared, tmp_path, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    (prepared / "cases/zero-vs-missing/trial/src/daw/bio_cli.py").write_text("changed after preparation")
    with pytest.raises(ValueError, match="prepared source changed"):
        run(prepared, fake_codex(tmp_path / "fake-codex"))
    assert not (prepared / "cases/zero-vs-missing/execution.json").exists()
    assert read_json(prepared / "manifest.json")["state"] == "failed"


def test_invalid_review_is_visible_without_becoming_scientific_success(prepared):
    folder = prepared / "review"
    folder.mkdir()
    write_json(folder / "provenance.json", {"state": "invalid_review", "error": "evidence locator does not exist"})
    report = build_report(prepared)
    assert report["review_state"] == "invalid_review" and report["review"] is None
    assert "evidence locator does not exist" in (prepared / "report.html").read_text()
    assert next(c for c in report["cases"][0]["checks"] if c["id"] == "scientific_review")["status"] == "unknown"


def test_partial_malformed_events_remain_auditable(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"type":"turn.started"}\nnot-json\n{"type":"item.started","item":{"id":"x","type":"command_execution"}}\n{"type":')
    before = path.read_bytes()
    parsed = parse_events(path)
    assert parsed["malformed_lines"] == [2, 4]
    assert parsed["turns_completed"] == 0 and parsed["usage"] is None
    assert parsed["items"][0]["id"] == "x"
    assert path.read_bytes() == before


def test_timeout_retains_partial_transcript(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("fixture")
    result = execute([sys.executable, "-c", "import time; print('partial event', flush=True); time.sleep(30)"],
                     prompt, tmp_path, tmp_path, dict(os.environ), timeout=0.3)
    assert result["state"] == "timed_out" and result["returncode"] != 0
    assert (tmp_path / "events.jsonl").read_text() == "partial event\n"
    assert read_json(tmp_path / "execution.json")["state"] == "timed_out"


def test_log_budget_terminates_and_preserves_output(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("fixture")
    result = execute([sys.executable, "-c", "import time; print('x'*10000, flush=True); time.sleep(30)"],
                     prompt, tmp_path, tmp_path, dict(os.environ), timeout=5, max_log_bytes=100)
    assert result["state"] == "log_budget_exceeded"
    assert (tmp_path / "events.jsonl").stat().st_size > 100


def test_input_and_code_mutation_are_detected(prepared):
    folder = prepared / "cases/zero-vs-missing"
    blob = read_json(folder / "baseline.json")["blob"][0]
    damaged = folder / "trial/workspace" / blob["path"]
    damaged.chmod(0o644)  # Deliberate tampering with the test copy, which normally is read-only.
    damaged.write_text("changed input bytes")
    (folder / "trial/src/daw/bio_cli.py").write_text("changed source")
    report = build_report(prepared)
    checks = {c["id"]: c["status"] for c in report["cases"][0]["checks"]}
    assert checks["preserved_inputs"] == checks["project_unchanged"] == "fail"


def test_path_traversal_and_symlink_evidence_are_rejected(prepared, tmp_path):
    with pytest.raises(ValueError):
        Case(id="../../escape", question="question")
    with pytest.raises(ValueError):
        safe_path(prepared, "../outside")
    outside = tmp_path / "private.txt"
    outside.write_text("not evaluation evidence")
    (prepared / "linked.txt").symlink_to(outside)
    with pytest.raises(ValueError):
        safe_path(prepared, "linked.txt")


def valid_review():
    return {"summary": "Fixture review, not a model result", "strengths": [], "findings": [{
        "case_id": "zero-vs-missing", "category": "evaluation", "severity": "low",
        "observation": "The subject has not run", "evidence": [{"path": "report.json", "locator": "/cases/0/status"}],
        "suggested_change": "Run the prepared case", "validation_test": "A recorded execution exists"}],
        "unresolved": ["Scientific behavior untested"], "next_experiments": ["Launch a subject"]}


def test_review_citations_must_exist_and_dont_change_mechanical_scientific_status(prepared, tmp_path):
    build_report(prepared)
    value = valid_review()
    validate_review(prepared, value)
    value["findings"][0]["evidence"][0]["locator"] = "/cases/99/status"
    with pytest.raises(ValueError, match="pointer"):
        validate_review(prepared, value)
    value = valid_review()
    value["findings"][0]["evidence"][0]["locator"] = "line:999999"
    with pytest.raises(ValueError, match="line"):
        validate_review(prepared, value)
    authored = tmp_path / "review.json"
    write_json(authored, valid_review())
    review_run(prepared, authored=authored)
    report = read_json(prepared / "report.json")
    assert report["review_state"] == "recorded"
    assert next(c for c in report["cases"][0]["checks"] if c["id"] == "scientific_review")["status"] == "unknown"


def test_comparison_retains_missing_cases_and_unknown_timings(prepared, tmp_path):
    build_report(prepared)
    after = tmp_path / "after"
    after.mkdir()
    report = read_json(prepared / "report.json")
    extra = {**report["cases"][0], "case_id": "additional-case"}
    report["cases"].append(extra)
    write_json(after / "report.json", report)
    result = compare(prepared, after)
    assert next(c for c in result["cases"] if c["case_id"] == "additional-case")["missing"] == "before"
    assert next(c for c in result["cases"] if c["case_id"] == "zero-vs-missing")["wall_seconds_delta"] is None


def test_cli_argv_keeps_permissions_bounded_and_model_literal(tmp_path):
    argv = codex_command("/path with spaces/codex", tmp_path, tmp_path / "final.md", model="literal;model", public=False)
    assert argv[0] == "/path with spaces/codex" and argv[argv.index("--model") + 1] == "literal;model"
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert 'web_search="disabled"' in argv and "sandbox_workspace_write.network_access=false" in argv
    assert not any("dangerously" in arg for arg in argv)
