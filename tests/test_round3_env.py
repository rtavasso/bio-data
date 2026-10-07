"""Round three: the agent environment. PDF text, the pinned R image helper, Hermes approvals, platform config
refresh of sealed Hermes configs, and the Hermes deterministic-fallback form. Offline: no docker, no model."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from daw import hermes
from daw.commons import records, replication, sandbox
from daw.harness.hermes import ADAPTER as HERMES
from daw.util import canonical

SCRIPTS = Path(__file__).resolve().parents[1] / ".agents/skills/bio-research/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- PDF text ------------------------------------------------------------------------------------

def minimal_pdf(pages):
    """A valid PDF whose pages draw the given lines of text (None: a page with no text, like a scan)."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        ops = "" if lines is None else "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(
            f"({line}) Tj T*" for line in lines) + " ET"
        objects.append(f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                       f"/Contents {len(objects)} 0 R >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_pdf_text_extracts_pages_writes_full_text_and_greps(tmp_path, capsys):
    pdf_text = load("pdf_text")
    path = tmp_path / "paper.pdf"
    path.write_bytes(minimal_pdf([["PMP22 duplication", "Schwann cells"], ["Table S2 counts"], None]))
    out = tmp_path / "paper.txt"
    assert pdf_text.main([str(path), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "status=partial_text pages=3" in printed and "pages without text (image-only?): [3]" in printed
    assert "p1: PMP22 duplication | Schwann cells" in printed
    text = out.read_text()
    assert "=== page 2 ===\nTable S2 counts" in text and "=== page 3 ===" in text
    assert pdf_text.main([str(path), "--grep", "schwann|table s2", "--pages", "1-2"]) == 0
    printed = capsys.readouterr().out
    assert "p1:2: Schwann cells" in printed and "p2:1: Table S2 counts" in printed and "grep hits: 2" in printed
    assert pdf_text.page_range("2,4-", 5) == [1, 3, 4] and pdf_text.page_range(None, 2) == [0, 1]
    with pytest.raises(ValueError):
        pdf_text.page_range("x", 3)
    with pytest.raises(SystemExit):
        pdf_text.main([str(path), "--max-chars", "20000"])


def test_pdf_text_reports_image_only_and_encrypted_pdfs(tmp_path, capsys):
    from pypdf import PdfReader, PdfWriter
    pdf_text = load("pdf_text")
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(minimal_pdf([None, None]))
    assert pdf_text.main([str(scan)]) == 2
    assert "status=no_text" in capsys.readouterr().out
    plain = tmp_path / "plain.pdf"
    plain.write_bytes(minimal_pdf([["secret result"]]))
    writer = PdfWriter()
    writer.append(PdfReader(plain))
    writer.encrypt("pw", algorithm="RC4-128")
    locked = tmp_path / "locked.pdf"
    with locked.open("wb") as stream:
        writer.write(stream)
    assert pdf_text.main([str(locked), "--out", str(tmp_path / "locked.txt")]) == 2
    printed = capsys.readouterr().out
    assert "status=encrypted" in printed and "secret result" not in printed
    assert not (tmp_path / "locked.txt").exists()


def test_trial_python_imports_pypdf(tmp_path):
    """./bin/python execs the runtime interpreter, which has pypdf as a base dependency."""
    from daw.agent_setup import copy_research_tools
    trial = tmp_path / "trial"
    trial.mkdir()
    copy_research_tools(trial, skill_names=("bio-research",))
    assert (trial / ".agents/skills/bio-research/scripts/pdf_text.py").is_file()
    result = subprocess.run([str(trial / "bin/python"), "-c", "import pypdf; print(pypdf.__version__)"],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip().startswith("6.")


# ---- R analysis in the pinned image ------------------------------------------------------------

FAKE_DOCKER = """#!{python}
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_DOCKER_LOG"]
with open(log, "a") as f:
    f.write(json.dumps(args) + "\\n")
if args[:2] == ["image", "inspect"]:
    if args[-1] == "missing:image":
        sys.stderr.write("Error: No such image")
        sys.exit(1)
    print(json.dumps("sha256:" + "ab" * 32) + " " + json.dumps(["colloquy-r-deseq2@sha256:" + "cd" * 32]))
    sys.exit(0)
if args[0] == "run":
    script_args = args[args.index("Rscript") + 3:]
    print("fitted 2 genes")
    if os.environ.get("FAKE_DOCKER_FAIL"):
        sys.stderr.write("Error in DESeq: design has no replicates")
        sys.exit(1)
    with open(script_args[-1], "w") as f:
        f.write("gene\\tlog2FoldChange\\nPMP22\\t1.0\\n")
    sys.exit(0)
sys.exit(2)
"""


@pytest.fixture
def question(tmp_path, monkeypatch):
    root = tmp_path / "workspace/questions/q1"
    (root / "scripts").mkdir(parents=True)
    (root / "inputs").mkdir()
    (root / "scripts/de.R").write_text("args <- commandArgs(TRUE)\n")
    (root / "inputs/counts.tsv").write_text("gene\ta\tb\nPMP22\t10\t20\n")
    docker = tmp_path / "bin/docker"
    docker.parent.mkdir()
    docker.write_text(FAKE_DOCKER.format(python=sys.executable))
    docker.chmod(0o755)
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(tmp_path / "docker.log"))
    monkeypatch.chdir(tmp_path)
    return root, docker


def docker_calls(tmp_path):
    return [json.loads(line) for line in (tmp_path / "docker.log").read_text().splitlines()]


def test_r_analysis_runs_in_the_image_and_writes_a_run_analysis_receipt(question, tmp_path, capsys):
    r_analysis = load("r_analysis")
    root, docker = question
    receipt = root / "outputs/de-execution-r001.json"
    status = r_analysis.run(receipt, [Path("workspace/questions/q1/outputs/de.tsv")],
                            ["--", "workspace/questions/q1/scripts/de.R", "workspace/questions/q1/inputs/counts.tsv",
                             "workspace/questions/q1/outputs/de.tsv"],
                            [Path("workspace/questions/q1/inputs/counts.tsv")], docker=str(docker), image="r:test")
    assert status == 0
    inspect, run = docker_calls(tmp_path)
    assert inspect[:2] == ["image", "inspect"] and inspect[-1] == "r:test"
    image_id = "sha256:" + "ab" * 32
    root_r = root.resolve()
    assert run[:4] == ["run", "--rm", "--network", "none"]
    assert f"{root_r}:{root_r}:ro" in run and f"{root_r / 'outputs'}:{root_r / 'outputs'}:rw" in run
    assert run[run.index("-w") + 1] == str(tmp_path.resolve())
    at = run.index(image_id)
    assert run[at + 1:at + 4] == ["Rscript", "--vanilla", str(root_r / "scripts/de.R")]
    value = json.loads(receipt.read_text())
    for key in ("version", "argv", "cwd", "producer", "code_sha256", "started", "finished", "inputs", "exit_code",
                "outputs", "code_unchanged", "inputs_unchanged", "complete"):
        assert key in value, key
    assert value["complete"] is True and value["exit_code"] == 0 and value["inputs_unchanged"] is True
    assert value["outputs"][0]["written"] is True and value["outputs"][0]["sha256"]
    assert value["runtime"]["image_id"] == image_id and value["runtime"]["repo_digests"]
    assert records._receipt_shape(value)
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed["event"] == "analysis_executed" and printed["complete"] is True
    assert printed["receipt"] == str(receipt.resolve()) and "fitted 2 genes" in printed["stdout_tail"]
    # The stream recognisers accept r_analysis.py where they accept run_analysis.py.
    command = ("./bin/python .agents/skills/bio-research/scripts/r_analysis.py --receipt "
               "workspace/questions/q1/outputs/de-execution-r001.json --output x -- workspace/questions/q1/scripts/de.R")
    assert replication.helper_segment(command)["helper"] == "r_analysis.py"
    parsed = {"items": [{"name": "terminal", "command": command, "line": 7, "aggregated_output": json.dumps(printed)}]}
    [found] = replication.stream_executions(parsed)
    assert found["helper"] == "r_analysis.py" and found["sha256"] == printed["sha256"]
    [call] = records.stream_calls(parsed, tmp_path)
    assert call["printed"][0]["sha256"] == printed["sha256"]
    assert not records.ANALYSIS.search("python scripts/our_analysis.py")


def test_r_analysis_failure_prints_stderr_and_refuses_bad_calls(question, tmp_path, monkeypatch, capsys):
    r_analysis = load("r_analysis")
    root, docker = question
    monkeypatch.setenv("FAKE_DOCKER_FAIL", "1")
    status = r_analysis.run(root / "outputs/r.json", [root / "outputs/de.tsv"],
                            ["Rscript", str(root / "scripts/de.R"), str(root / "outputs/de.tsv")], docker=str(docker))
    assert status == 1
    printed = json.loads(capsys.readouterr().out.strip())
    assert printed["complete"] is False and "no replicates" in printed["stderr_tail"]
    with pytest.raises(ValueError, match="not available"):
        r_analysis.run(root / "outputs/r2.json", [root / "outputs/de.tsv"], [str(root / "scripts/de.R")],
                       docker=str(docker), image="missing:image")
    assert not (root / "outputs/r2.json").exists()
    with pytest.raises(ValueError, match="saved R script"):
        r_analysis.run(root / "outputs/r3.json", [root / "outputs/de.tsv"], ["python", "x.py"], docker=str(docker))
    with pytest.raises(ValueError, match="inside the question folder"):
        r_analysis.run(root / "outputs/r4.json", [tmp_path / "elsewhere.tsv"], [str(root / "scripts/de.R")],
                       docker=str(docker))


def test_r_analysis_native_uses_local_rscript(question, tmp_path, monkeypatch, capsys):
    r_analysis = load("r_analysis")
    root, _ = question
    rscript = tmp_path / "rbin/Rscript"
    rscript.parent.mkdir()
    rscript.write_text(f"#!{sys.executable}\nimport sys\nif sys.argv[1] == '--version':\n    print('Rscript 4.6.1')\n"
                       "else:\n    open(sys.argv[-1], 'w').write('ok')\n")
    rscript.chmod(0o755)
    monkeypatch.setenv("PATH", f"{rscript.parent}{os.pathsep}{os.environ['PATH']}")
    out = root / "outputs/n.tsv"
    assert r_analysis.run(root / "outputs/n.json", [out], [str(root / "scripts/de.R"), str(out)], native=True) == 0
    value = json.loads((root / "outputs/n.json").read_text())
    assert value["runtime"]["kind"] == "native" and "4.6.1" in value["runtime"]["version"] and value["complete"]


# ---- Hermes approvals and platform config refresh -----------------------------------------------

def test_prepare_home_turns_off_the_safety_scan_for_one_shot_turns(tmp_path):
    trial = tmp_path / "agent/trial"
    trial.mkdir(parents=True)
    hermes.prepare_home(trial, "m", "xhigh", "p")
    config = json.loads((trial / ".hermes/config.yaml").read_text())
    assert config["approvals"] == {"mode": "off", "single_query_mode": "approve"}
    assert config["security"] == {"tirith_enabled": False, "protected_instruction_files": True}
    assert config["model"] == {"default": "m", "provider": "p"} and config["agent"]["reasoning_effort"] == "xhigh"
    assert config["auxiliary"]["compression"]["no_progress_timeout"] == 600 and config["_config_version"] == 12


OCT5 = {"_config_version": 12, "agent": {"max_turns": 0, "reasoning_effort": "xhigh"},
        "auxiliary": {"background_review": {"enabled": False}}, "curator": {"enabled": False},
        "display": {"interface": "cli"}, "memory": {"memory_enabled": True, "user_profile_enabled": False},
        "model": {"default": "gpt-6-astra", "provider": "openai-codex"}, "skills": {"project_discovery": True},
        "terminal": {"backend": "local", "cwd": "/trial"}}
# Hermes's first launch: the version migrated and an empty plugin allow-list appended in flow YAML.
MIGRATED = (json.dumps({**OCT5, "_config_version": 49})[:-1] + ", plugins: {enabled: []}}").encode()


def test_flow_yaml_rewrite_parses_and_its_migration_is_benign():
    assert hermes.load_config(MIGRATED) == {**OCT5, "_config_version": 49, "plugins": {"enabled": []}}
    assert hermes.load_config(b'{"a": "x, y: z", b: 1}') == {"a": "x, y: z", "b": 1}
    assert hermes.config_migration("config.yaml", canonical(OCT5), MIGRATED)
    tampered = MIGRATED.replace(b'"xhigh"', b'"low"')
    assert not hermes.config_migration("config.yaml", canonical(OCT5), tampered)
    plugin = MIGRATED.replace(b"enabled: []", b"enabled: [evil]")
    assert not hermes.config_migration("config.yaml", canonical(OCT5), plugin)
    assert not hermes.config_migration("config.yaml", canonical(OCT5), canonical(OCT5))


def test_refresh_merges_platform_keys_and_keeps_agent_keys():
    sealed = {**OCT5, "skills": {"project_discovery": True, "custom": "agent-owned"}}
    result = hermes.refresh_config("config.yaml", canonical(sealed), None)
    assert result["updated_keys"] == ["auxiliary.compression", "compression", "memory", "approvals", "security"]
    merged = json.loads(result["bytes"])
    assert merged["memory"]["memory_enabled"] is False and merged["approvals"]["mode"] == "off"
    assert merged["auxiliary"] == {"background_review": {"enabled": False},
                                   "compression": {"no_progress_timeout": 600, "timeout": 900}}
    assert merged["skills"]["custom"] == "agent-owned" and merged["model"]["default"] == "gpt-6-astra"
    assert hermes.refresh_config("config.yaml", result["bytes"], None)["bytes"] is None  # idempotent
    moved = hermes.refresh_config("config.yaml", result["bytes"], None, {"model": "m2", "effort": "high"})
    assert moved["updated_keys"] == ["model.default", "agent.reasoning_effort"]
    assert hermes.refresh_config("mcp.json", b"{}", None) is None and hermes.refresh_config("config.yaml", b"[", None) is None


def stage(tmp_path, sealed_bytes, home_bytes=None):
    trial = tmp_path / "agent/trial"
    (trial / ".hermes").mkdir(parents=True)
    (trial / ".hermes/config.yaml").write_bytes(sealed_bytes)
    sandbox.seal_harness_config(trial, HERMES)
    if home_bytes is not None:
        (trial / ".hermes/config.yaml").write_bytes(home_bytes)
    return trial


def test_turn_reseals_existing_agents_with_current_platform_keys(tmp_path):
    trial = stage(tmp_path, canonical(OCT5))
    receipt = sandbox.turn_harness_config(trial, HERMES)
    assert receipt["platform_keys_updated"] == {"config.yaml": ["auxiliary.compression", "compression", "memory",
                                                                "approvals", "security"]}
    assert receipt["restored_before_turn"] == [] and receipt["migration_adopted"] == []
    folder = sandbox.harness_config_dir(trial)
    sealed = (folder / "config.yaml").read_bytes()
    assert (trial / ".hermes/config.yaml").read_bytes() == sealed
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["files"]["config.yaml"]["sha256"] == receipt["files"]["config.yaml"] and manifest["refreshed"]
    again = sandbox.turn_harness_config(trial, HERMES)
    assert again["platform_keys_updated"] == {} and again["restored_before_turn"] == []


def test_hermes_migration_is_adopted_not_reported_as_a_config_change(tmp_path):
    trial = stage(tmp_path, canonical(OCT5), MIGRATED)
    receipt = sandbox.turn_harness_config(trial, HERMES)
    assert receipt["migration_adopted"] == ["config.yaml"] and receipt["restored_before_turn"] == []
    config = json.loads((trial / ".hermes/config.yaml").read_text())
    assert config["_config_version"] == 49 and config["plugins"] == {"enabled": []}
    assert config["approvals"]["single_query_mode"] == "approve" and config["security"]["tirith_enabled"] is False
    # A fresh v12 seal migrated during the turn is recorded as a migration, not a change.
    fresh = stage(tmp_path / "three", canonical({**OCT5}))
    turn = sandbox.turn_harness_config(fresh, HERMES)
    sealed = json.loads((sandbox.harness_config_dir(fresh) / "config.yaml").read_text())
    (fresh / ".hermes/config.yaml").write_bytes((json.dumps({**sealed, "_config_version": 49})[:-1]
                                                 + ", plugins: {enabled: []}}").encode())
    checked = sandbox.check_harness_config(fresh, HERMES, turn)
    assert checked["changed_during_turn"] == [] and checked["migrated_during_turn"] == ["config.yaml"]
    # An agent edit is still a change, and is restored before the next turn.
    (fresh / ".hermes/config.yaml").write_text(json.dumps({**sealed, "approvals": {"mode": "manual"}}))
    assert sandbox.check_harness_config(fresh, HERMES, turn)["changed_during_turn"] == ["config.yaml"]
    assert sandbox.turn_harness_config(fresh, HERMES)["restored_before_turn"] == ["config.yaml"]


# ---- compaction fallback form -------------------------------------------------------------------

HEAD = "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted into the summary below.\n\n"


def test_only_the_hermes_fallback_form_counts_as_a_fallback():
    fallback = (HEAD + "## Historical Task Snapshot\nUser asked: ...\n\n## Goal\nRecovered from a deterministic "
                "fallback because the LLM context summarizer was unavailable. Continue from the protected recent messages.")
    summary = (HEAD + "## Goal\nFinish the PMP22 dosage analysis.\n\n## Errors & Fixes\n- Prior fallback reported "
               "secrets redacted; details unavailable from deterministic fallback.\n")
    assert records.is_fallback(fallback) and not records.is_fallback(summary)
    assert not records.is_fallback(None) and records.FALLBACK_MARKER in fallback
