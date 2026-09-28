import copy
import csv
import os
import sys

import pytest

from benchmarks.agent.mechanisms import COVERAGE_FIELDS, MechanismMap, coverage_rows
from benchmarks.agent.capture import execute
from benchmarks.agent.models import MECHANISM_CRITERIA
from benchmarks.agent.fixtures import seed
from benchmarks.agent.report import build_report
from benchmarks.agent.review import review_run, validate_review
from benchmarks.agent.runner import prepare
from daw.catalog import Workspace
from daw.util import read_json, write_json
from daw.work import create_question


def hypothesis():
    return {"revision": 1, "scope": {"target": "synthetic endpoint", "assumptions": "no biological claims"},
        "nodes": [{"id": "a", "label": "candidate process", "kind": "process"},
                  {"id": "b", "label": "measured endpoint", "kind": "readout"}],
        "edges": [{"id": "ab", "source": "a", "target": "b", "mechanism": "unverified hypothesis",
                   "context": "synthetic", "status": "hypothesis", "evidence": []}],
        "frontier": [{"node": "a", "question": "What regulates this process?", "priority": "high",
                      "reason": "Could change the explanation", "status": "open"}], "changes": []}


def coverage(path, **overrides):
    row = {"edge_ids": "ab", "alternatives": "direct versus shared-cause explanation", "observation": "controlled perturbation",
           "file_or_accession": "", "analysis": "compare endpoint response with matched controls",
           "inspection_status": "not_searched", "source_locator": "", "result_or_limitation": "unresolved",
           "next_action": "find suitable measurements", **overrides}
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, delimiter="\t", fieldnames=COVERAGE_FIELDS)
        writer.writeheader()
        writer.writerow(row)


def test_network_references_and_attribution_without_rejecting_feedback():
    graph = hypothesis()
    graph["edges"].append({**graph["edges"][0], "id": "ba", "source": "b", "target": "a"})
    assert len(MechanismMap.model_validate(graph).edges) == 2  # Feedback is legitimate structure, not proof.
    graph["edges"][0]["target"] = "unknown"
    with pytest.raises(ValueError, match="unknown node"):
        MechanismMap.model_validate(graph)
    graph = hypothesis()
    graph["edges"][0]["status"] = "supported"
    with pytest.raises(ValueError, match="attributed evidence"):
        MechanismMap.model_validate(graph)


def test_coverage_does_not_promote_unlocated_or_uncited_data_to_analysis(tmp_path):
    graph = MechanismMap.model_validate(hypothesis())
    path = tmp_path / "coverage.tsv"
    coverage(path)
    assert coverage_rows(path, graph)[0]["inspection_status"] == "not_searched"
    coverage(path, inspection_status="analyzed")
    with pytest.raises(ValueError, match="source identity"):
        coverage_rows(path, graph)
    coverage(path, inspection_status="inspected", file_or_accession="synthetic.tsv")
    with pytest.raises(ValueError, match="evidence locator"):
        coverage_rows(path, graph)
    coverage(path, edge_ids="unrelated")
    with pytest.raises(ValueError, match="unknown or empty edge"):
        coverage_rows(path, graph)


@pytest.fixture
def mechanism_run(tmp_path):
    root = prepare("mechanisms", output=tmp_path)
    folder = root / "cases/pmp22-regulatory-system"
    ws = Workspace(folder / "trial/workspace")
    with ws.writer():
        q = create_question(ws, "Synthetic audit fixture")
        outputs = ws.root / "questions" / q["question"] / "outputs"
        write_json(outputs / "mechanisms.initial.json", hypothesis())
        graph = hypothesis()
        graph.update(revision=2, changes=[{"reason": "Fixture records retained uncertainty", "evidence": []}])
        write_json(outputs / "mechanisms.json", graph)
        coverage(outputs / "evidence-coverage.tsv")
    ws.close()
    write_json(folder / "execution.json", {"state": "exited"})
    (folder / "events.jsonl").write_text('{"type":"turn.completed","usage":{}}\n')
    build_report(root)
    return root


def test_mechanism_structure_never_establishes_scientific_success(mechanism_run):
    report = read_json(mechanism_run / "report.json")
    checks = {c["id"]: c["status"] for c in report["cases"][0]["checks"]}
    assert checks["mechanism_map"] == checks["mechanism_revision"] == checks["evidence_coverage"] == "pass"
    assert checks["scientific_review"] == "unknown" and report["review_state"] == "pending"
    prompt = (mechanism_run / "cases/pmp22-regulatory-system/prompt.txt").read_text()
    assert "What is the full regulatory system for PMP22?" in prompt
    assert "source-backed investigation" not in prompt  # Private rubric is not supplied as an answer hint.
    assert (mechanism_run / "cases/pmp22-regulatory-system/trial/.agents/skills/bio-mechanism-exploration/references/artifacts.md").exists()


def complete_review():
    return {"summary": "Synthetic rubric test", "strengths": [], "findings": [], "unresolved": ["Not a biological evaluation"],
            "next_experiments": [], "assessments": [{"case_id": "pmp22-regulatory-system", "criterion": criterion,
                "verdict": "unresolved", "justification": "Fixture has no real source investigation",
                "evidence": [{"path": "cases/pmp22-regulatory-system/events.jsonl", "locator": "line:1"}]}
                for criterion in MECHANISM_CRITERIA]}


def test_reviewer_must_cover_all_dimensions_with_real_citations(mechanism_run, tmp_path):
    value = complete_review()
    validate_review(mechanism_run, value)
    incomplete = copy.deepcopy(value)
    incomplete["assessments"].pop()
    with pytest.raises(ValueError, match="exactly once"):
        validate_review(mechanism_run, incomplete)
    duplicate = copy.deepcopy(value)
    duplicate["assessments"].append(duplicate["assessments"][0])
    with pytest.raises(ValueError, match="exactly once"):
        validate_review(mechanism_run, duplicate)
    missing = copy.deepcopy(value)
    missing["assessments"][0]["evidence"][0]["locator"] = "line:2"
    with pytest.raises(ValueError, match="line"):
        validate_review(mechanism_run, missing)
    authored = tmp_path / "review.json"
    write_json(authored, value)
    review_run(mechanism_run, authored=authored)
    report = read_json(mechanism_run / "report.json")
    assert len(report["review"]["assessments"]) == 6
    assert "recursive_exploration" in (mechanism_run / "report.html").read_text()
    assert next(c for c in report["cases"][0]["checks"] if c["id"] == "scientific_review")["status"] == "unknown"


def test_synthetic_challenge_preserves_actual_measurements_and_keeps_oracle_private(tmp_path):
    root = prepare("mechanism-challenges", output=tmp_path)
    folder = root / "cases/upstream-and-rna-fate"
    trial = folder / "trial"
    context = read_json(trial / "inputs/source-context.json")
    assert context["synthetic"] is True
    with (trial / "inputs/process-screen.tsv").open() as stream:
        rows = {row["condition"]: row for row in csv.DictReader(stream, delimiter="\t")}
    assert rows["U_inhibited"]["R_abundance"] == "1" and rows["U_inhibited"]["R_activity"] == "0.4"
    assert rows["D_inhibited"]["T_nascent_RNA"] == "1" and rows["D_inhibited"]["T_RNA_half_life"] == "2"
    assert "State C2 only" in context["assay_notes"]["other-context-screen.tsv"]
    assert "D inhibition changes" not in (folder / "prompt.txt").read_text()
    assert not (trial / "benchmarks").exists()
    report = build_report(root)
    assert next(c for c in report["cases"][0]["checks"] if c["id"] == "mechanism_map")["status"] == "unknown"


def test_wall_clock_gap_cannot_extend_a_live_evaluation(tmp_path, monkeypatch):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("fixture")
    ticks = iter([100.0, 1000.0, 1000.0])
    monkeypatch.setattr("benchmarks.agent.capture.time.time", lambda: next(ticks, 1000.0))
    result = execute([sys.executable, "-c", "import time; time.sleep(30)"], prompt, tmp_path, tmp_path, dict(os.environ), timeout=5)
    assert result["state"] == "timed_out"
    assert result["wall_seconds"] == 900 and result["monotonic_seconds"] < 5


def test_seed_copy_can_start_new_work_without_modifying_original(ws, tmp_path):
    with ws.writer():
        source = ws.put_bytes(b"preserved source bytes")
    original_questions = ws.rows("SELECT id FROM question")
    root = tmp_path / "trial/workspace"
    seed(root, "empty", ws.root)
    copied = Workspace(root)
    try:
        with copied.writer():
            q = create_question(copied, "Independent copied workspace investigation")
        assert q["question"]
        assert copied.blob_path(source).read_bytes() == ws.blob_path(source).read_bytes()
        assert ws.rows("SELECT id FROM question") == original_questions
    finally:
        copied.close()
