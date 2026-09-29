import json
import runpy
from pathlib import Path

import pytest

from daw.research_records import check_handoff
from daw.util import copy_snapshot_file, file_hash, write_json
from daw.work import create_question


def test_full_handoff_rejects_unsupported_analysis_and_missing_prediction_fields(ws):
    with ws.writer():
        q = create_question(ws, "Handoff integrity")
    folder = Path(q["path"])
    value = {"revision": 1, "scope": "fixture", "status": "in_progress", "stopping_reason": "unfinished",
        "items": [{"id": "literature", "priority": "high", "question": "What is known?", "alternatives": ["a", "b"],
            "readout": "measurements", "assets": [], "prerequisites": [], "status": "analyzed", "artifacts": [],
            "finding": "Read a paper", "limitation": "no computation", "next_action": "inspect data", "blocker_evidence": []}]}
    write_json(folder / "outputs/investigations.json", value)
    assert not check_handoff(folder)["valid"]
    value["items"][0]["status"] = "deferred"
    write_json(folder / "outputs/investigations.json", value)
    assert check_handoff(folder)["valid"]
    write_json(folder / "outputs/discoveries.json", {"revision": 1, "scope": "fixture", "known_baseline": "unknown",
        "budget_allocation": "unlimited", "stopping_reason": "unfinished", "candidates": [{"id": "missing-fields"}],
        "no_candidates_reason": ""})
    before = (folder / "outputs/discoveries.json").read_bytes()
    checked = check_handoff(folder)
    assert not checked["valid"] and checked["errors"][0]["record"] == "discovery_ledger"
    assert (folder / "outputs/discoveries.json").read_bytes() == before


@pytest.mark.parametrize("body", ["raise SystemExit(2)", "pass"])
def test_failed_or_noop_producer_cannot_claim_stale_output(tmp_path, body):
    helper = runpy.run_path(str(Path(__file__).parents[1] / ".agents/skills/bio-research/scripts/run_analysis.py"))
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "analyze.py"
    script.write_text(body)
    output = tmp_path / "result.txt"
    output.write_text("stale")
    receipt = tmp_path / "receipt.json"
    import sys
    assert helper["run"](receipt, [output], [sys.executable, str(script)]) != 0
    assert not json.loads(receipt.read_text())["complete"]
    assert output.read_text() == "stale"


def test_snapshot_copies_remain_independent(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"immutable source")
    copy_snapshot_file(source, target)
    assert file_hash(source) == file_hash(target)
    assert source.stat().st_ino != target.stat().st_ino
    target.write_bytes(b"changed copy")
    assert source.read_bytes() == b"immutable source"
