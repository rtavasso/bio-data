import copy
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.agent.discoveries import DiscoveryLedger, inspect_discoveries
from benchmarks.agent.models import DISCOVERY_CRITERIA, MECHANISM_CRITERIA
from benchmarks.agent.report import build_report, inventory
from benchmarks.agent.review import validate_review
from benchmarks.agent.runner import prepare
from daw.util import file_hash, read_json, write_json


HELPER = Path(__file__).resolve().parents[1] / ".agents/skills/bio-hypothesis-discovery/scripts/seal_prediction.py"
LINK_HELPER = HELPER.with_name("check_prediction_links.py")


def prediction():
    return {"candidate_id": "test-lead", "claim": "Synthetic A changes T beyond state response",
            "context": "Fictional cells", "baseline_model": "T follows the state program",
            "discovery_sources": ["fictional-study-1"], "validation_sources": ["fictional-study-2"],
            "prior_exposure": "Validation metadata only; model prior knowledge is unassessed",
            "prediction": "A loss reduces T relative to the prespecified state panel",
            "analysis_plan": "Compare independent sample means of log ratios with fixed panel P",
            "success_rule": "All independent contrasts have negative log ratios",
            "failure_rule": "All independent contrasts have positive log ratios",
            "confounder_checks": ["Inspect sample composition and library quality"],
            "selection_and_multiplicity": "One selected hypothesis; descriptive directional test"}


def ledger():
    return {"revision": 1, "scope": "Synthetic discovery integrity fixture",
            "known_baseline": "State response could explain T", "budget_allocation": "Half reserved for testing",
            "stopping_reason": "Fixture completed; no real biological inference", "no_candidates_reason": "",
            "candidates": [{"id": "test-lead", "claim": prediction()["claim"], "context": "Fictional cells",
                "kind": "biological", "status": "candidate", "alternatives": ["A-specific", "General state"],
                "discovery_artifacts": ["artifact_discovery"], "prediction_lock": None, "prediction_sha256": None,
                "validation_mode": "not_tested", "validation_artifacts": [], "validation_result": "Not tested",
                "independence_assessment": "Unknown until sample metadata checked",
                "novelty": {"status": "unresolved", "closest_prior_work": [], "searches": [], "limitation": "No literature audit"},
                "limitations": "Fictional fixture", "next_test": "Independent directional test"}]}


def test_prediction_helper_preserves_bytes_and_refuses_overwrite_or_nonfinite(tmp_path):
    source, destination = tmp_path / "draft.json", tmp_path / "sealed/test.json"
    write_json(source, prediction())
    result = subprocess.run([sys.executable, str(HELPER), str(source), str(destination)],
                            capture_output=True, text=True, check=True)
    receipt = json.loads(result.stdout)
    assert receipt["sha256"] == file_hash(source) == file_hash(destination)
    assert destination.read_bytes() == source.read_bytes()
    value = prediction()
    value["prediction"] = "Changed after looking at validation"
    write_json(source, value)
    again = subprocess.run([sys.executable, str(HELPER), str(source), str(destination)], capture_output=True)
    assert again.returncode == 1 and file_hash(destination) == receipt["sha256"]
    invalid = prediction() | {"optional_value": float("nan")}
    source.write_text(json.dumps(invalid))
    with pytest.raises(ValueError):
        runpy.run_path(str(HELPER))["seal"](source, tmp_path / "bad.json")
    assert not (tmp_path / "bad.json").exists()
    invalid = prediction()
    del invalid["failure_rule"]
    write_json(source, invalid)
    with pytest.raises(ValueError, match="failure_rule"):
        runpy.run_path(str(HELPER))["seal"](source, tmp_path / "bad.json")
    for members in ([], "test-lead", ["test-lead", "test-lead"], ["not an id"], [42]):
        write_json(source, prediction() | {"candidate_ids": members})
        with pytest.raises(ValueError, match="candidate_ids"):
            runpy.run_path(str(HELPER))["seal"](source, tmp_path / "bad.json")
        assert not (tmp_path / "bad.json").exists()


def test_discovery_record_does_not_force_positive_findings_or_invent_evidence():
    value = ledger()
    value["candidates"] = []
    with pytest.raises(ValueError, match="empty ledger"):
        DiscoveryLedger.model_validate(value)
    value["no_candidates_reason"] = "Inspected matrix has no independent samples; see preserved design metadata"
    DiscoveryLedger.model_validate(value)
    value = ledger()
    c = value["candidates"][0]
    c["status"] = "supported_in_scope"
    with pytest.raises(ValueError, match="requires a test"):
        DiscoveryLedger.model_validate(value)
    c.update(status="contradicted", validation_mode="retrospective", validation_artifacts=["artifact_validation"],
             validation_result="All source contrasts have opposite direction")
    DiscoveryLedger.model_validate(value)  # Rejection is a legitimate outcome, not a failed workflow.
    c["novelty"]["status"] = "not_found_in_scoped_search"
    with pytest.raises(ValueError, match="closest prior"):
        DiscoveryLedger.model_validate(value)
    c["novelty"]["closest_prior_work"] = [{"source": "Synthetic report", "locator": "table 1", "relationship": "State effect only"}]
    with pytest.raises(ValueError, match="preserved searches"):
        DiscoveryLedger.model_validate(value)
    c["novelty"]["status"] = "unresolved"
    c["validation_mode"] = "prospective"
    with pytest.raises(ValueError, match="sealed prediction"):
        DiscoveryLedger.model_validate(value)
    c.update(validation_mode="retrospective", prediction_id="test-family")
    with pytest.raises(ValueError, match="prediction_id requires"):
        DiscoveryLedger.model_validate(value)


def test_ledger_inspection_checks_exact_bytes_links_and_search_evidence(tmp_path):
    question = {"id": "q_test", "path": "questions/q_test"}
    folder = tmp_path / "workspace" / question["path"]
    (folder / "outputs").mkdir(parents=True)
    source = folder / "outputs/draft.json"
    lock = folder / "outputs/prediction.json"
    write_json(source, prediction())
    receipt = runpy.run_path(str(HELPER))["seal"](source, lock)
    value = ledger()
    c = value["candidates"][0]
    c.update(prediction_lock="outputs/prediction.json", prediction_sha256=receipt["sha256"],
             validation_mode="prospective", validation_artifacts=["artifact_validation"],
             status="contradicted", validation_result="Opposite direction")
    path = folder / "outputs/discoveries.json"
    write_json(path, value)
    parsed = {"items": [{"type": "command_execution", "exit_code": 0, "line": 5,
                         "command": "python seal_prediction.py draft.json prediction.json",
                         "aggregated_output": json.dumps(receipt)}]}
    ids = {"artifact_discovery", "artifact_validation"}
    record = inspect_discoveries(tmp_path, question, ids, parsed)
    assert record["candidates"][0]["seal_receipt_lines"] == [5]
    assert record["candidates"][0]["novelty"] == "unresolved"
    without_transcript = inspect_discoveries(tmp_path, question, ids, {"items": []})
    assert without_transcript["candidates"][0]["seal_receipt_lines"] == []
    with pytest.raises(ValueError, match="unregistered"):
        inspect_discoveries(tmp_path, question, {"artifact_discovery"}, parsed)
    c["novelty"]["searches"] = [{"query": "T and A", "date": "2026-09-27", "evidence": "inputs/missing.json"}]
    write_json(path, value)
    with pytest.raises(ValueError, match="search evidence"):
        inspect_discoveries(tmp_path, question, ids, parsed)
    c["novelty"]["searches"] = []
    write_json(path, value)
    write_json(lock, prediction() | {"prediction": "Post hoc revision"})
    with pytest.raises(ValueError, match="recorded hash"):
        inspect_discoveries(tmp_path, question, ids, parsed)
    write_json(lock, [])
    c["prediction_sha256"] = file_hash(lock)
    write_json(path, value)
    with pytest.raises(ValueError, match="another candidate"):
        inspect_discoveries(tmp_path, question, ids, parsed)


def test_panel_seal_requires_explicit_binding_and_predeclared_membership(tmp_path):
    question = {"id": "q_test", "path": "questions/q_test"}
    folder = tmp_path / "workspace" / question["path"]
    (folder / "outputs").mkdir(parents=True)
    source, lock = folder / "outputs/draft.json", folder / "outputs/panel.json"
    members = ["test-lead", "second-lead", "third-lead"]
    write_json(source, prediction() | {"candidate_id": "test-family", "candidate_ids": members})
    receipt = runpy.run_path(str(HELPER))["seal"](source, lock)
    value = ledger()
    first = value["candidates"][0]
    first.update(prediction_lock="outputs/panel.json", prediction_sha256=receipt["sha256"],
                 prediction_id="test-family", validation_mode="prospective",
                 validation_artifacts=["artifact_validation"], status="contradicted",
                 validation_result="Opposite direction in the synthetic test")
    value["candidates"] = [first | {"id": member} for member in members]
    path = folder / "outputs/discoveries.json"
    write_json(path, value)
    parsed = {"items": [{"type": "command_execution", "exit_code": 0, "line": 7,
                         "command": "python seal_prediction.py draft.json panel.json",
                         "aggregated_output": json.dumps(receipt)}]}
    ids = {"artifact_discovery", "artifact_validation"}
    records = inspect_discoveries(tmp_path, question, ids, parsed)["candidates"]
    assert [c["id"] for c in records] == members
    assert all(c["prediction_id"] == "test-family" and c["seal_receipt_lines"] == [7] for c in records)
    first = value["candidates"][0]
    first["id"] = "unrelated-claim"
    write_json(path, value)
    with pytest.raises(ValueError, match="not an explicit member"):
        inspect_discoveries(tmp_path, question, ids, parsed)
    first["id"] = members[0]
    for binding in (None, "wrong-family"):
        first["prediction_id"] = binding
        write_json(path, value)
        with pytest.raises(ValueError, match="another candidate"):
            inspect_discoveries(tmp_path, question, ids, parsed)
    first["prediction_id"] = "test-family"
    # A declared panel ID alone cannot retrofit membership into a historical lock.
    write_json(lock, prediction() | {"candidate_id": "test-family"})
    for c in value["candidates"]:
        c["prediction_sha256"] = file_hash(lock)
    write_json(path, value)
    with pytest.raises(ValueError, match="not an explicit member"):
        inspect_discoveries(tmp_path, question, ids, parsed)


def test_continuation_link_check_preserves_legacy_panel_bytes_and_negative_results(tmp_path):
    question = {"id": "q_test", "path": "questions/q_test"}
    folder = tmp_path / "workspace" / question["path"]
    (folder / "outputs").mkdir(parents=True)
    lock = folder / "outputs/panel.json"
    write_json(lock, prediction() | {"candidate_id": "original-panel"})
    original_lock = lock.read_bytes()
    value = ledger()
    first = value["candidates"][0]
    first.update(prediction_lock="outputs/panel.json", prediction_sha256=file_hash(lock),
                 validation_mode="prospective", validation_artifacts=["artifact_validation"],
                 status="contradicted", validation_result="Opposite direction in this synthetic test")
    value["candidates"] = [first | {"id": name} for name in ("first-lead", "second-lead", "third-lead")]
    path = folder / "outputs/discoveries.json"
    write_json(path, value)
    original_ledger = path.read_bytes()
    result = subprocess.run([sys.executable, str(LINK_HELPER), str(folder)], capture_output=True, text=True)
    assert result.returncode == 1
    check = json.loads(result.stdout)
    assert len(check["errors"]) == 3 and not check["valid"]
    assert path.read_bytes() == original_ledger and lock.read_bytes() == original_lock
    ids = {"artifact_discovery", "artifact_validation"}
    with pytest.raises(ValueError, match="another candidate"):
        inspect_discoveries(tmp_path, question, ids, {"items": []})

    # Correct the current representation at the original panel level, without
    # retroactively declaring members in its seal or discarding negative results.
    archived = folder / "outputs/discoveries.r001.json"
    archived.write_bytes(original_ledger)
    outcomes = [{"id": c["id"], "status": c["status"], "result": c["validation_result"]}
                for c in value["candidates"]]
    value.update(revision=2, candidates=[first | {"id": "original-panel", "member_outcomes": outcomes}])
    write_json(path, value)
    assert runpy.run_path(str(LINK_HELPER))["check_links"](folder)["valid"]
    record = inspect_discoveries(tmp_path, question, ids, {"items": []})
    assert record["candidates"][0]["status"] == "contradicted"
    assert record["candidates"][0]["seal_receipt_lines"] == []  # No timing credit invented.
    assert archived.read_bytes() == original_ledger and lock.read_bytes() == original_lock
    assert len(read_json(path)["candidates"][0]["member_outcomes"]) == 3


def test_partial_inspection_exposes_new_claim_without_forgiving_inherited_error(tmp_path):
    question = {"id": "q_test", "path": "questions/q_test"}
    folder = tmp_path / "workspace" / question["path"]
    (folder / "outputs").mkdir(parents=True)
    old_lock, new_lock = folder / "outputs/old.json", folder / "outputs/new.json"
    write_json(old_lock, prediction() | {"candidate_id": "old-panel"})
    write_json(new_lock, prediction())
    value = ledger()
    c = value["candidates"][0]
    c.update(prediction_lock="outputs/new.json", prediction_sha256=file_hash(new_lock),
             validation_mode="prospective", validation_artifacts=["artifact_validation"])
    broken = c | {"id": "old-member", "prediction_lock": "outputs/old.json", "prediction_sha256": file_hash(old_lock)}
    baseline = value | {"candidates": [broken]}
    value["candidates"] = [broken, c]
    write_json(folder / "outputs/discoveries.json", value)
    parsed = {"items": [{"type": "command_execution", "exit_code": 0, "line": 9,
                        "command": "python seal_prediction.py draft.json new.json",
                        "aggregated_output": json.dumps({"event": "prediction_sealed", "candidate_id": "test-lead",
                                                        "sha256": file_hash(new_lock)})}]}
    ids = {"artifact_discovery", "artifact_validation"}
    result = inspect_discoveries(tmp_path, question, ids, parsed, collect_errors=True, baseline_value=baseline)
    assert result["error"] and len(result["candidate_errors"]) == 1
    assert result["candidate_errors"][0]["prediction_reference_unchanged_from_baseline"]
    assert result["candidates"][0]["id"] == "test-lead"
    assert result["candidates"][0]["prediction_sha256"] == file_hash(new_lock)
    assert result["candidates"][0]["seal_receipt_lines"] == [9]
    with pytest.raises(ValueError, match="another candidate"):
        inspect_discoveries(tmp_path, question, ids, parsed)  # Strict acceptance is unchanged.


@pytest.mark.parametrize("problem", ["changed_bytes", "escape", "undeclared_member", "missing_lock"])
def test_link_check_rejects_invalid_prediction_references(tmp_path, problem):
    folder = tmp_path / "question"
    (folder / "outputs").mkdir(parents=True)
    lock = folder / "outputs/prediction.json"
    write_json(lock, prediction())
    value = ledger()
    c = value["candidates"][0]
    c.update(prediction_lock="outputs/prediction.json", prediction_sha256=file_hash(lock),
             validation_mode="prospective")
    if problem == "changed_bytes":
        lock.write_bytes(lock.read_bytes() + b"\n")
    elif problem == "escape":
        outside = tmp_path / "outside.json"
        outside.write_bytes(lock.read_bytes())
        link = folder / "outside-link.json"
        link.symlink_to(outside)
        c["prediction_lock"] = link.name
    elif problem == "undeclared_member":
        write_json(lock, prediction() | {"candidate_id": "panel", "candidate_ids": ["another-lead"]})
        c.update(prediction_id="panel", prediction_sha256=file_hash(lock))
    else:
        c.update(prediction_lock=None, prediction_sha256=None)
    write_json(folder / "outputs/discoveries.json", value)
    result = runpy.run_path(str(LINK_HELPER))["check_links"](folder)
    assert not result["valid"] and len(result["errors"]) == 1


def test_discovery_suite_and_mixed_review_keep_scientific_claims_unresolved(tmp_path):
    root = prepare("discovery", output=tmp_path, profile="deep")
    folder = root / "cases/pmp22-specific-regulation"
    assert (folder / "trial/.agents/skills/bio-hypothesis-discovery/scripts/seal_prediction.py").is_file()
    report = build_report(root)
    assert next(c for c in report["cases"][0]["checks"] if c["id"] == "discovery_ledger")["status"] == "unknown"
    (folder / "events.jsonl").write_text('{"type":"turn.completed","usage":{}}\n')
    value = {"summary": "No scientific outcome in offline fixture", "strengths": [], "findings": [],
             "unresolved": ["Science"], "next_experiments": [], "assessments": [
                 {"case_id": "pmp22-specific-regulation", "criterion": c, "verdict": "unresolved",
                  "justification": "Fixture only", "evidence": [{"path": "cases/pmp22-specific-regulation/events.jsonl", "locator": "line:1"}]}
                 for c in DISCOVERY_CRITERIA]}
    validate_review(root, value)
    incomplete = copy.deepcopy(value)
    incomplete["assessments"].pop()
    with pytest.raises(ValueError, match="exactly once"):
        validate_review(root, incomplete)
    duplicate = copy.deepcopy(value)
    duplicate["assessments"].append(duplicate["assessments"][0])
    with pytest.raises(ValueError, match="exactly once"):
        validate_review(root, duplicate)
    # A mixed suite must independently cover both rubrics, never silently drop one.
    manifest = read_json(root / "manifest.json")
    manifest["selected_cases"].append("mechanism")
    manifest["suite"]["cases"].append({"id": "mechanism", "review_rubric": "mechanism-exploration"})
    write_json(root / "manifest.json", manifest)
    with pytest.raises(ValueError, match="exactly once"):
        validate_review(root, value)
    value["assessments"] += [{**copy.deepcopy(value["assessments"][0]), "case_id": "mechanism", "criterion": c}
                             for c in MECHANISM_CRITERIA]
    validate_review(root, value)


def test_preview_budget_does_not_hide_later_analysis_provenance(tmp_path):
    folder = tmp_path / "workspace/questions/q_test"
    (folder / "inputs").mkdir(parents=True)
    (folder / "scripts").mkdir()
    for i in range(3):
        (folder / "inputs" / f"{i}.txt").write_text("Preserved source")
    script = folder / "scripts/new_analysis.py"
    script.write_text("print(2 + 3)\n")
    result = inventory(tmp_path, limit=2)
    assert result["complete"] and result["omitted_previews"] == 2
    assert result["files"][-1]["sha256"] == file_hash(script)
    bounded = inventory(tmp_path, limit=2, file_limit=3)
    assert not bounded["complete"] and bounded["omitted_files"] == 1
