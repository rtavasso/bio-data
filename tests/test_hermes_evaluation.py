import json
import os
import sqlite3
import sys
import tomllib

import pytest

from benchmarks.agent import hermes
from benchmarks.agent.runner import prepare, run
from daw.catalog import Workspace
from daw.util import read_json


@pytest.fixture
def seed(tmp_path):
    source = tmp_path / "seed"
    Workspace.create(source).close()
    (source / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0.0\n")
    return source


def fake_hermes(path):
    path.write_text(f"#!{sys.executable}\n" + '''import json, os, sys, sqlite3
from pathlib import Path
if '--version' in sys.argv:
    print('fixture-hermes 1')
    raise SystemExit(0)
home=Path(os.environ['HERMES_HOME'])
config=json.loads((home/'config.yaml').read_text())
assert config['agent']['reasoning_effort']=='xhigh'
assert config['agent']['max_turns']==0
assert not config['auxiliary']['background_review']['enabled']
assert config['memory']['memory_enabled'] is False and not config['curator']['enabled']  # spec v3 V18
assert 'memory' not in sys.argv[sys.argv.index('--toolsets')+1].split(',')
assert sys.argv[sys.argv.index('--query-file')+1]=='-'
assert sys.stdin.read()
(home/'memories/MEMORY.md').write_text('Use source artifact with context limits.')
(home/'skills/learned').mkdir(parents=True,exist_ok=True)
(home/'skills/learned/SKILL.md').write_text('A tested preparation method.')
(home/'auth.json').write_text('fixture credential must not be exported')
with sqlite3.connect(home/'state.db') as db:
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS messages(body TEXT)')
    db.execute('INSERT INTO messages VALUES (?)',('full tool result '+ 'x'*6000,))
for event in [
 {'type':'system','subtype':'init','session_id':'fixture-session'},
 {'type':'tool_use','name':'terminal','tool_call_id':'t1','input':{'command':'python analysis.py'}},
 {'type':'tool_result','name':'terminal','tool_call_id':'t1','output':json.dumps({'exit_code':2,'output':'failure'}),'is_error':False},
 {'type':'result','exit_code':0,'text':'Fixture completion only; scientific quality untested.','tokens':{'input':12,'output':5,'cache_read':3}}
]: print(json.dumps(event),flush=True)
''')
    path.chmod(0o755)
    return str(path)


def test_full_checkpoint_roundtrip_and_prior_work_control(tmp_path, seed, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    root = prepare(output=tmp_path / "runs", runtime="hermes", seed_workspace=seed, cases=["zero-vs-missing"])
    run(root, fake_hermes(tmp_path / "hermes"))
    case = read_json(root / "report.json")["cases"][0]
    assert case["status"] == "complete"
    assert case["failed_commands"][0]["exit_code"] == 2
    assert case["usage"]["input_tokens"] == 12
    checkpoint = root / "cases/zero-vs-missing/checkpoint"
    receipt = read_json(checkpoint / "checkpoint.json")
    assert receipt["completed"] and receipt["restorable"]
    assert not (checkpoint / "agent/auth.json").exists()
    assert not (checkpoint / "agent/state.db-wal").exists()
    assert not (checkpoint / "agent/state.db-shm").exists()
    assert "skills/learned/SKILL.md" in receipt["changes"]["added"]
    with sqlite3.connect(checkpoint / "agent/state.db") as db:
        assert len(db.execute("SELECT body FROM messages").fetchone()[0]) > 5000
    later = prepare(output=tmp_path / "runs", runtime="hermes", suite="learning", cases=["learning-transfer"], seed_checkpoint=checkpoint)
    home = later / "cases/learning-transfer/trial/.hermes"
    assert (home / "memories/MEMORY.md").read_text() == (checkpoint / "agent/memories/MEMORY.md").read_text()
    assert not (home / "auth.json").exists()
    control = prepare(output=tmp_path / "runs", runtime="hermes", suite="learning", cases=["learning-transfer"], seed_workspace=checkpoint / "workspace")
    assert not (control / "cases/learning-transfer/trial/.hermes/memories/MEMORY.md").exists()
    assert read_json(control / "cases/learning-transfer/baseline.json")["blob"] == read_json(later / "cases/learning-transfer/baseline.json")["blob"]
    (checkpoint / "agent/memories/MEMORY.md").write_text("tampered")
    with pytest.raises(ValueError, match="learning checkpoint changed"):
        prepare(output=tmp_path / "runs", runtime="hermes", suite="learning", cases=["learning-transfer"], seed_checkpoint=checkpoint)


def test_hermes_preparation_tamper_blocks_launch(tmp_path, seed, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    root = prepare(output=tmp_path / "runs", runtime="hermes", seed_workspace=seed, cases=["zero-vs-missing"])
    (root / "cases/zero-vs-missing/trial/.hermes/memories/injected.md").write_text("unexpected memory")
    with pytest.raises(ValueError, match="learning state changed"):
        run(root, fake_hermes(tmp_path / "hermes"))
    assert not (root / "cases/zero-vs-missing/execution.json").exists()


def test_parser_does_not_infer_shell_success_from_tool_completion(tmp_path):
    events = [
        {"type": "tool_use", "name": "terminal", "input": {"command": "analysis"}},
        {"type": "tool_result", "name": "terminal", "output": "truncated...", "is_error": False},
        {"type": "result", "exit_code": 1, "error": "iteration limit", "text": "partial"}]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n{partial")
    parsed = hermes.parse(path)
    assert parsed["turns_completed"] == 0 and parsed["errors"]
    assert parsed["items"][0]["exit_code"] is None
    assert parsed["malformed_lines"] == [4]
    assert parsed["usage"]["input_tokens"] is None


def test_snapshot_rejects_links_and_excludes_credentials(tmp_path):
    home = tmp_path / "home"
    (home / "memories").mkdir(parents=True)
    (home / "auth.json").write_text("secret")
    (home / ".env").write_text("secret")
    (home / "memories/note.md").write_text("evidence pointer")
    hashes = hermes.snapshot_state(home, tmp_path / "snapshot")
    assert set(hashes) == {"memories/note.md"}
    (home / "skills").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        hermes.snapshot_state(home, tmp_path / "bad-snapshot")


def test_environment_and_literal_arguments(tmp_path):
    env = hermes.environment({**os.environ, "HERMES_MODEL": "wrong", "BIO_WORKSPACE": "correct"}, tmp_path)
    assert "HERMES_MODEL" not in env
    assert env["BIO_WORKSPACE"] == "correct"
    assert env["HERMES_HOME"] == str(tmp_path / ".hermes")
    args = hermes.command("hermes", tmp_path, "literal;model", "openai-codex")
    assert args[args.index("--model") + 1] == "literal;model"
    assert "--yolo" not in args


def test_disk_reserve_override_is_local_and_configuration_is_sealed(tmp_path, seed, monkeypatch):
    monkeypatch.setenv("DAW_LIVE", "1")
    original = (seed / "config.toml").read_bytes()
    root = prepare(output=tmp_path / "runs", runtime="hermes", seed_workspace=seed, suite="learning",
                   cases=["learning-transfer"], disk_reserve_bytes=5 * 2**30)
    config = root / "cases/learning-transfer/trial/workspace/config.toml"
    budgets = tomllib.loads(config.read_text())["budgets"]
    assert budgets["reserve_bytes"] == 5 * 2**30 and budgets["reserve_fraction"] == 0
    assert (seed / "config.toml").read_bytes() == original
    config.write_text(config.read_text().replace("5368709120", "0"))
    with pytest.raises(ValueError, match="workspace configuration changed"):
        run(root, fake_hermes(tmp_path / "hermes"))
    with pytest.raises(ValueError, match="disk reserve"):
        prepare(disk_reserve_bytes=-1)


def test_concurrent_tools_without_ids_do_not_get_fabricated_execution_credit(tmp_path):
    events = [
        {"type": "tool_use", "name": "terminal", "input": {"command": "first"}},
        {"type": "tool_use", "name": "terminal", "input": {"command": "second"}},
        {"type": "tool_result", "name": "terminal", "output": '{"exit_code":0}', "is_error": False},
        {"type": "tool_result", "name": "terminal", "output": '{"exit_code":1}', "is_error": True}]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(map(json.dumps, events)))
    assert all(item["exit_code"] is None for item in hermes.parse(path)["items"])


def test_runtime_status_preserves_order_but_malformed_events_still_fail(tmp_path):
    path = tmp_path / "events.jsonl"
    raw = '{"type":"system","session_id":"one"}\n  ⟳ compacting context…\n{broken\n{"type":"result","exit_code":0,"text":"done"}\n'
    path.write_text(raw)
    parsed = hermes.parse(path)
    assert parsed["malformed_lines"] == [3]
    assert [(e["line"], e["event"]["type"]) for e in parsed["events"]] == [(1, "system"), (2, "runtime_status"), (4, "result")]
    assert path.read_text() == raw
