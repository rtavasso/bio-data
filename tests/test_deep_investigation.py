import copy
import json
import os
import shutil
import subprocess
import tomllib

import pytest

from benchmarks.agent.investigations import InvestigationQueue, analysis_activity, inspect_queue, invoked_scripts
from benchmarks.agent.models import ResearchBudget
from benchmarks.agent.report import build_report
from benchmarks.agent.runner import prepare, subject_environment
from daw.artifacts import register_artifact
from daw.catalog import Workspace
from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
from daw.util import read_json, write_json
from daw.work import create_question, sync_work


def queue():
    return {"revision": 1, "scope": "Synthetic uncertainty", "status": "in_progress", "stopping_reason": "Continue work",
        "items": [{"id": "one", "priority": "high", "question": "Which explanation fits?",
            "alternatives": ["activity", "abundance"], "readout": "paired measurements", "assets": [], "prerequisites": [],
            "status": "open", "artifacts": [], "finding": "", "limitation": "", "next_action": "inspect measurements", "blocker_evidence": []}]}


def test_deep_budgets_match_prompt_manifest_and_workspace(tmp_path):
    limits = ResearchBudget(requests=87, asset_bytes=128 * 2**20, total_bytes=900 * 2**20)
    root = prepare("mechanisms-deep", output=tmp_path, profile="deep", budget=limits, timeout=7200)
    m = read_json(root / "manifest.json")
    assert m["timeout_seconds"] == 7200 and m["research_budget"] == limits.model_dump()
    folder = root / "cases/pmp22-regulatory-system"
    config = tomllib.loads((folder / "trial/workspace/config.toml").read_text())["budgets"]
    assert config["requests"] == 87 and config["asset_bytes"] == limits.asset_bytes and config["bundle_bytes"] == limits.total_bytes
    prompt = (folder / "prompt.txt").read_text()
    assert "87 requests" in prompt and str(limits.total_bytes) in prompt
    assert "Verify each analyzed" not in prompt  # Private review focus is not subject task text.
    with pytest.raises(ValueError, match="per-file"):
        ResearchBudget(asset_bytes=10, total_bytes=9)
    with pytest.raises(ValueError):
        ResearchBudget(requests=-1)


@pytest.mark.parametrize("profile", ["pilot", "deep"])
def test_default_research_limits_are_unlimited_in_manifest_and_reopened_workspace(tmp_path, profile, ws):
    config = ws.root / "config.toml"
    inherited = "[budgets]\nasset_bytes=128\nbundle_bytes=256\nrequests=2\nreserve_bytes=0\nreserve_fraction=0.0\n"
    config.write_text(inherited)
    root = prepare("mechanisms", output=tmp_path, profile=profile, seed_workspace=ws.root)
    manifest = read_json(root / "manifest.json")
    assert manifest["timeout_seconds"] == 0
    assert manifest["research_budget"] == {"requests": 0, "asset_bytes": 0, "total_bytes": 0}
    ws = Workspace(root / "cases/pmp22-regulatory-system/trial/workspace")
    try:
        assert ws.budgets.requests == ws.budgets.asset_bytes == ws.budgets.bundle_bytes == 0
    finally:
        ws.close()
    assert config.read_text() == inherited


def test_research_caps_can_be_set_independently_without_old_ceiling():
    assert ResearchBudget(asset_bytes=32 * 2**30).total_bytes == 0
    assert ResearchBudget(total_bytes=64 * 2**30).asset_bytes == 0
    assert ResearchBudget(requests=10001).requests == 10001


@pytest.mark.parametrize("flags,expected", [([], (0, 0, 0, 0)),
    (["--timeout", "7200", "--requests", "10001", "--asset-mib", "0", "--total-mib", "32768"],
     (7200, 10001, 0, 32 * 2**30))])
def test_cli_deep_profile_keeps_unlimited_defaults_and_independent_overrides(tmp_path, flags, expected):
    result = subprocess.run([os.sys.executable, "-m", "benchmarks.agent", "prepare", "--suite", "mechanisms",
        "--profile", "deep", "--output", str(tmp_path), *flags], capture_output=True, text=True, check=True)
    from pathlib import Path
    manifest = read_json(Path(json.loads(result.stdout)["run"]) / "manifest.json")
    budget = manifest["research_budget"]
    assert (manifest["timeout_seconds"], budget["requests"], budget["asset_bytes"], budget["total_bytes"]) == expected


def test_wrapped_python_survives_login_shell_and_keeps_tls_verification(tmp_path):
    root = prepare("mechanisms", output=tmp_path / "root with spaces")
    m = read_json(root / "manifest.json")
    folder = root / "cases/pmp22-regulatory-system"
    trial = folder / "trial"
    env = subject_environment(trial, m)
    env.pop("SSL_CERT_FILE", None)
    code = "import ssl,sys,json; c=ssl.create_default_context(); print(json.dumps([sys.executable,c.check_hostname,c.verify_mode==ssl.CERT_REQUIRED,c.cert_store_stats()['x509_ca']]))"
    # Invoke the exact wrapper through a login shell, including paths containing spaces in fixture roots.
    shell = shutil.which("zsh") or shutil.which("bash")
    import shlex
    result = subprocess.run([shell, "-lc", "./bin/python -c " + shlex.quote(code)], cwd=trial, env=env,
                            capture_output=True, text=True, check=True)
    executable, hostname, verify, roots = json.loads(result.stdout)
    assert executable == m["python"] and hostname and verify and roots > 0
    env["SSL_CERT_FILE"] = str(tmp_path / "missing-ca.pem")
    failed = subprocess.run([str(trial / "bin/python"), "-c", "import ssl;ssl.create_default_context()"], env=env,
                            capture_output=True, text=True)
    assert failed.returncode != 0  # Never bypass or silently replace an explicit trust setting.


def test_queue_cannot_hide_deferred_work_or_invent_analysis_and_blockers(tmp_path):
    value = queue()
    value["status"] = "bounded_complete"
    with pytest.raises(ValueError, match="not bounded complete"):
        InvestigationQueue.model_validate(value)
    value["items"][0].update(status="analyzed", finding="result")
    with pytest.raises(ValueError, match="registered results"):
        InvestigationQueue.model_validate(value)
    value["items"][0].update(status="blocked", limitation="Missing design metadata", blocker_evidence=["inputs/receipt.json"])
    folder = tmp_path / "workspace/questions/q_test"
    (folder / "outputs").mkdir(parents=True)
    write_json(folder / "outputs/investigations.json", value)
    question = {"id": "q_test", "path": "questions/q_test"}
    with pytest.raises(ValueError, match="absent"):
        inspect_queue(tmp_path, question, set())
    (folder / "inputs").mkdir()
    write_json(folder / "inputs/receipt.json", {"design": "not supplied"})
    assert inspect_queue(tmp_path, question, set())["status"] == "bounded_complete"
    value["items"][0]["blocker_evidence"] = ["../../outside"]
    write_json(folder / "outputs/investigations.json", value)
    with pytest.raises(ValueError, match="relative path"):
        inspect_queue(tmp_path, question, set())


def test_acquisition_activity_separates_source_identity_and_unique_new_bytes(tmp_path):
    baseline = {"artifact": [], "asset_revision": [{"id": "old", "blob": "a"}], "blob": [{"sha256": "a", "size": 5}]}
    state = {"artifact": [], "asset_revision": [*baseline["asset_revision"], {"id": "new-source-same-bytes", "blob": "a"},
        {"id": "new-one", "blob": "b"}, {"id": "new-two", "blob": "b"}, {"id": "not-acquired", "blob": None}],
        "blob": [*baseline["blob"], {"sha256": "b", "size": 7}]}
    activity = analysis_activity(tmp_path, baseline, state, [], {"items": []}, [])
    assert len(activity["new_acquired_assets"]) == 3
    assert activity["new_unique_asset_bytes"] == 7
    legacy = copy.deepcopy(baseline)
    del legacy["asset_revision"]
    activity = analysis_activity(tmp_path, legacy, state, [], {"items": []}, [])
    assert not activity["acquisition_baseline_available"] and activity["new_acquired_assets"] == []


def test_public_status_checker_catches_observed_frontier_drift_without_rewriting(tmp_path):
    import runpy
    from pathlib import Path
    from typing import get_args

    from benchmarks.agent.investigations import Investigation
    from benchmarks.agent.mechanisms import COVERAGE_FIELDS, Edge, Frontier

    script = Path(__file__).resolve().parents[1] / ".agents/skills/bio-mechanism-exploration/scripts/check_statuses.py"
    checker = runpy.run_path(str(script))
    assert checker["FRONTIER"] == set(get_args(Frontier.model_fields["status"].annotation))
    assert checker["EDGE"] == set(get_args(Edge.model_fields["status"].annotation))
    assert checker["ITEM"] == set(get_args(Investigation.model_fields["status"].annotation))
    assert checker["QUEUE"] == set(get_args(InvestigationQueue.model_fields["status"].annotation))
    assert checker["COVERAGE_FIELDS"] == set(COVERAGE_FIELDS)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    graph = {"edges": [], "frontier": [{"status": "analyzed_but_unresolved", "reason": "Uncertainty remains"}]}
    write_json(outputs / "mechanisms.json", graph)
    value = queue()
    value["items"][0].update(status="blocked", limitation="Missing assay", blocker_evidence=["inputs/receipt.json"])
    write_json(outputs / "investigations.json", value)
    (outputs / "evidence-coverage.tsv").write_text("\t".join(COVERAGE_FIELDS) + "\n" +
        "\t".join("unavailable" if k == "inspection_status" else "fixture" for k in COVERAGE_FIELDS) + "\n")
    before = (outputs / "mechanisms.json").read_bytes()
    result = subprocess.run([os.sys.executable, str(script), str(tmp_path)], capture_output=True, text=True)
    record = json.loads(result.stdout)
    assert result.returncode == 1 and not record["valid"]
    assert len(record["errors"]) == 1 and "frontier/0/status" in record["errors"][0]
    assert (outputs / "mechanisms.json").read_bytes() == before
    graph["frontier"][0].update(status="investigated", disposition="analyzed_but_unresolved")
    write_json(outputs / "mechanisms.json", graph)
    assert checker["check"](tmp_path)["valid"]  # Nuance stays in extra fields; queue 'blocked' remains valid.
    (outputs / "evidence-coverage.tsv").write_text("branch\tinspection_status\nRNA\tsource_inspected\n")
    invalid_coverage = checker["check"](tmp_path)
    assert not invalid_coverage["valid"]
    assert any("missing columns" in e for e in invalid_coverage["errors"])
    assert any("source_inspected" in e for e in invalid_coverage["errors"])


def test_continuation_counts_only_new_work_and_executed_result_evidence(ws, tmp_path):
    with ws.writer():
        q = create_question(ws, "Persistent question")
        from pathlib import Path
        original = Path(q["path"])
        (original / "LABBOOK.md").write_text("Prior work, retained")
        sync_work(ws, q["question"], summary="baseline")
    root = prepare("mechanisms-deep", output=tmp_path, seed_workspace=ws.root, continue_question=q["question"], timeout=30)
    folder = root / "cases/pmp22-regulatory-system"
    write_json(folder / "execution.json", {"state": "exited"})
    (folder / "events.jsonl").write_text('{"type":"turn.completed","usage":{}}\n')
    before = build_report(root)["cases"][0]
    checks = {c["id"]: c["status"] for c in before["checks"]}
    assert checks["notebook"] == checks["script"] == checks["registered_output"] == checks["executed_analysis"] == "fail"
    copied = Workspace(folder / "trial/workspace")
    try:
        local = copied.root / "questions" / q["question"]
        script = local / "scripts/analyze.py"
        script.write_text("import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text(str(sum(map(int,Path(sys.argv[1]).read_text().split()))))\n")
        output = local / "outputs/sum.txt"
        with copied.writer():
            source = copied.put_bytes(b"2 3")
        command = [read_json(root / "manifest.json")["python"], str(script), str(copied.blob_path(source)), str(output)]
        subprocess.run(command, check=True)
        with copied.writer():
            registration = register_artifact(copied, output, ArtifactRegistration(title="Actual synthetic analysis",
                summary="Sum literal source values", derivation=Derivation(inputs=[ObjectInput(blob=source)],
                    code=[copied.put_file(script, "code")], parameters={}, references=[], environment={"fixture": True})), question=q["question"])
            (local / "LABBOOK.md").write_text("Prior work, retained\nNew analysis: 2 + 3 = 5\n")
            sync_work(copied, q["question"], summary="New computation")
        value = queue()
        value["items"][0].update(status="analyzed", artifacts=[registration["artifact"]], finding="Sum is 5")
        value["status"] = "bounded_complete"
        write_json(local / "outputs/investigations.json", value)
        # Registering an output and writing a script alone does not establish execution evidence.
        report = build_report(root)["cases"][0]
        assert next(c for c in report["checks"] if c["id"] == "executed_analysis")["status"] == "fail"
        # A successful heredoc can write reproduction instructions without running them.
        import shlex
        documentation = "cat <<'DOC' > REPRODUCE.md\n" + shlex.join(command) + "\nDOC"
        mentions = [{"type": "item.completed", "item": {"type": "command_execution", "id": "documentation", "exit_code": 0,
            "command": "/bin/zsh -lc " + shlex.quote(documentation), "aggregated_output": ""}},
            {"type": "turn.completed", "usage": {}}]
        (folder / "events.jsonl").write_text("\n".join(json.dumps(e) for e in mentions) + "\n")
        report = build_report(root)["cases"][0]
        assert next(c for c in report["checks"] if c["id"] == "executed_analysis")["status"] == "fail"
        assert report["activity"]["new_registered_results"][0]["mention_lines"] == [1]
        assert report["activity"]["new_registered_results"][0]["command_lines"] == []
        # A trailing display succeeds despite the actual analysis failing. Existing
        # output bytes and a matching script must not hide that process failure.
        failing = command[:2] + [str(local / "missing-input"), str(output)]
        masked = shlex.join(failing) + "\ncat " + shlex.quote(str(output))
        masked_result = subprocess.run(["/bin/sh", "-c", masked], capture_output=True, text=True)
        assert masked_result.returncode == 0 and "FileNotFoundError" in masked_result.stderr
        failed_event = {"type": "item.completed", "item": {"type": "command_execution", "id": "masked-failure",
            "exit_code": 0, "command": "/bin/sh -c " + shlex.quote(masked),
            "aggregated_output": masked_result.stdout + masked_result.stderr}}
        (folder / "events.jsonl").write_text(json.dumps(failed_event) + '\n{"type":"turn.completed","usage":{}}\n')
        report = build_report(root)["cases"][0]
        assert next(c for c in report["checks"] if c["id"] == "executed_analysis")["status"] == "fail"
        assert report["activity"]["new_registered_results"][0]["mention_lines"] == [1]
        events = [failed_event, {"type": "item.completed", "item": {"type": "command_execution", "id": "execution", "exit_code": 0,
            "command": shlex.join(command), "aggregated_output": ""}}, {"type": "turn.completed", "usage": {}}]
        (folder / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
        report = build_report(root)["cases"][0]
        checks = {c["id"]: c["status"] for c in report["checks"]}
        assert checks["executed_analysis"] == checks["notebook"] == checks["investigation_queue"] == "pass"
        assert report["activity"]["new_registered_results"][0]["command_lines"] == [2]
        assert checks["scientific_review"] == "unknown"
        assert (original / "LABBOOK.md").read_text() == "Prior work, retained"
        assert output.read_text() == "5"
        # Even a valid queue cannot cite an arbitrary or unlinked artifact.
        bad = copy.deepcopy(value)
        bad["items"][0]["artifacts"] = ["artifact_missing"]
        write_json(local / "outputs/investigations.json", bad)
        report = build_report(root)["cases"][0]
        assert next(c for c in report["checks"] if c["id"] == "investigation_queue")["status"] == "fail"
    finally:
        copied.close()
    assert os.path.exists(original / "LABBOOK.md")


def test_successful_script_leads_exclude_masked_shell_status():
    assert invoked_scripts("python good.py && cat result", successful_only=True) == {"good.py"}
    assert invoked_scripts("python one.py; python two.py", successful_only=True) == {"two.py"}
    assert invoked_scripts("python one.py\npython two.py", successful_only=True) == {"two.py"}
    for command in ("python bad.py; cat result", "python bad.py || true", "python bad.py | cat",
                    "python bad.py |& cat", "python bad.py &", "if false; then\npython bad.py\nfi",
                    "python bad.py\ncat <<'DOC'\npython fake.py\nDOC"):
        assert invoked_scripts(command, successful_only=True) == set()
