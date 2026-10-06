"""Real-data fixtures (C0): redaction, exclusions, verification, and that the archive still serves."""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daw.commons.app import create_app
from daw.commons.fixture import build_fixture, redact_stream_line, verify_fixture
from daw.community import Community
from daw.util import DawError


def test_redaction_keeps_structure_and_exit_codes_but_not_outputs():
    result = json.dumps({"type": "tool_result", "name": "terminal", "tool_call_id": "c1",
                         "output": json.dumps({"output": "secret paper text " * 50, "exit_code": 2})})
    redacted = json.loads(redact_stream_line(result))
    inner = json.loads(redacted["output"])
    assert inner["exit_code"] == 2 and inner["output"].startswith("[redacted ") and "secret" not in redacted["output"]
    use = json.dumps({"type": "tool_use", "name": "write_file", "input": {"path": "scripts/a.py", "content": "x" * 5000}})
    cleaned = json.loads(redact_stream_line(use))
    assert cleaned["input"]["path"] == "scripts/a.py" and cleaned["input"]["content"].startswith("[redacted 5000 bytes")
    small = json.dumps({"type": "tool_use", "name": "write_file", "input": {"path": "a.py", "content": "print(1)"}})
    assert json.loads(redact_stream_line(small))["input"]["content"] == "print(1)"
    assert redact_stream_line("⟳ compacting context…\n") == "⟳ compacting context…"
    text = json.dumps({"type": "text", "text": "the agent's own final answer"})
    assert json.loads(redact_stream_line(text))["text"] == "the agent's own final answer"


def _unmark_demo(root):
    (Path(root) / "DEMO.json").unlink()


def test_fixture_excludes_downloaded_bytes_and_sessions_and_still_serves(demo, tmp_path):
    root, context = demo
    with pytest.raises(DawError, match="fixture_of_demo"):
        build_fixture(root, tmp_path / "refused")
    _unmark_demo(root)  # treat the demo as if it were a real commons for the copy rules
    with Community(root) as board:
        library = board.library
        library.put_bytes(b"downloaded dataset bytes", "source")
        kept = library.put_bytes(b"agent-written notebook text", "work")
        before = board.rows("SELECT id,trial FROM agent WHERE trial IS NOT NULL")
    out = tmp_path / "fixture"
    summary = build_fixture(root, out, name="demo-as-fixture")
    assert summary["real_data"] is True and summary["counts"]["runs"] >= 1 and summary["counts"]["agents"] == len(before)
    manifest = json.loads((out / "FIXTURE.json").read_text())
    assert manifest["format"] == "colloquy-fixture/1" and "files" in manifest
    # Dropped classes are absent as files but their rows remain, so identities still resolve.
    lib = sqlite3.connect(out / "library/catalog.sqlite")
    sources = [r[0] for r in lib.execute("SELECT sha256 FROM blob WHERE classification='source'")]
    assert sources and not any((out / "library/blobs/sha256" / s[:2] / s).exists() for s in sources)
    assert (out / "library/blobs/sha256" / kept[:2] / kept).is_file()
    assert lib.execute("SELECT count(*) FROM feature_term").fetchone()[0] == 0
    assert not list(out.rglob("agent-state")) and not list(out.rglob("transcript.md")) and not list(out.rglob("state.db"))
    assert not (out / "service").exists() and not (out / "secrets").exists() and not (out / "DEMO.json").exists()
    board_db = sqlite3.connect(out / "board.sqlite")
    assert board_db.execute("SELECT count(*) FROM post").fetchone()[0] == sqlite3.connect(root / "board.sqlite").execute("SELECT count(*) FROM post").fetchone()[0]
    names = {r[0] for r in board_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "credential" in names:
        assert board_db.execute("SELECT count(*) FROM credential").fetchone()[0] == 0
    for stream in out.rglob("events.jsonl"):
        for line in stream.read_text().splitlines():
            if line.startswith("{") and json.loads(line).get("type") == "tool_result":
                assert "[redacted " in json.loads(line)["output"]
    checked = verify_fixture(out)
    assert checked["verified"] and checked["untracked"] == []
    (out / "FIXTURE.json").touch()
    # The fixture is a real commons to every reader: the API serves it, demo-only commands refuse it.
    client = TestClient(create_app(out, local_user="reviewer", static_dir=out / "missing"))
    assert client.get("/api/health").status_code == 200
    posts = client.get("/api/posts?limit=5").json()
    assert posts["items"]
    assert client.get("/api/map").status_code == 200
    runs = client.get("/api/runs").json()
    run_id = runs["items"][0]["id"]
    timeline = client.get(f"/api/runs/{run_id}")
    assert timeline.status_code == 200 and timeline.json()["metrics"]["tool_calls"] >= 0
    assert client.get(f"/api/runs/{run_id}/messages").status_code != 200  # no session database in a fixture
    with pytest.raises(DawError, match="not_a_demo_commons"):
        from daw.commons.demo import _demo_root
        _demo_root(out)


def test_committed_cohort_fixture_verifies_and_serves_real_data(cohort):
    """The real PMP22 board, as committed: unchanged bytes, and every main screen's endpoint answers."""
    source = Path(__file__).resolve().parents[1] / "fixtures" / "pmp22-cohort"
    checked = verify_fixture(source)
    assert checked["verified"] and checked["untracked"] == [], checked
    manifest = json.loads((source / "FIXTURE.json").read_text())
    assert manifest["real_data"] is True and manifest["counts"]["runs"] == 97 and manifest["counts"]["agents"] == 25
    before = sqlite3.connect(cohort / "board.sqlite").execute("SELECT max(seq) FROM event").fetchone()[0]
    client = TestClient(create_app(cohort, local_user="local", static_dir=cohort / "missing"))
    posts = client.get("/api/posts?limit=5").json()
    assert len(posts["items"]) == 5
    post = client.get("/api/posts/post_3f7bd6e66753476fb33ec6d9da9cbcc8").json()
    assert len(post["evidence_artifacts"]) == 5 and post["numbers"]
    artifact = client.get("/api/artifacts/artifact_2898ce0c7c1ac558f70cd34012400744153963aa374c5db9c70d1595dfd5bfa8")
    assert artifact.status_code == 200 and artifact.json()["present"] is False  # 171 KB output stays out of the fixture
    question = client.get("/api/questions/agent_9582a6a5b1184e99bca212dd4c648363/q_e9e29d6eed344964")
    assert question.status_code == 200 and question.json()["notebook"]
    run = client.get("/api/runs/run_91d07fcfc16d45eda1454bcae17a5acf").json()
    assert run["metrics"]["suspended_seconds"] > 3600 and len(run["compactions"]) == 4
    assert client.get("/api/map?limit=10000").json()["truncated"] is False
    assert client.get("/api/frontier").json()["total"] >= 59
    assert client.get("/api/dashboard").json()["summary"]["runs"] == 97
    # Serving in local mode must not write to the board: the fixture was settled at build time (v2 spec C3).
    after = sqlite3.connect(cohort / "board.sqlite").execute("SELECT max(seq) FROM event").fetchone()[0]
    assert after == before
