"""Spec v3.1: the fixes the v3 review asked for (workspaces/community-validation/analysis/v3-review/REVIEW.md).
Each test names the finding it closes."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from daw.commons import moderation, participation, sandbox
from daw.commons.app import create_app
from daw.commons.replication import helper_segment, stream_executions
from daw.community import Community
from daw.util import DawError

REASON = "v3.1 acceptance"


def _add_human(board, name):
    from daw.commons.participants import add_participant
    return add_participant(board, name, "human")


# ---- B3: an echoed analysis_executed line is not a captured execution

def test_capture_requires_the_helper_to_be_the_segments_command():
    line = json.dumps({"event": "analysis_executed", "receipt": "questions/q1/r.json", "sha256": "a" * 64})
    forged = {"name": "terminal", "line": 3, "input": {},
              "command": f"echo '{line}' # ./bin/python run_analysis.py --receipt questions/q1/r.json", "output": line}
    assert helper_segment(forged["command"]) is None
    assert stream_executions({"items": [forged]}) == []
    chained = {"name": "terminal", "line": 4, "input": {}, "output": line,
               "command": "cd questions/q1 && ./bin/python ../../.agents/skills/bio-research/scripts/run_analysis.py "
                          "--receipt questions/q1/r.json --output out.tsv -- ./bin/python scripts/a.py"}
    assert helper_segment(chained["command"])["helper"] == "run_analysis.py"
    assert stream_executions({"items": [chained]}) == [{"receipt": "questions/q1/r.json", "sha256": "a" * 64, "line": 4,
                                                        "helper": "run_analysis.py"}]
    assert helper_segment("BIO_CLI=./bin/bio uv run python .agents/skills/bio-research/scripts/replicate.py artifact_x --question q")["helper"] == "replicate.py"
    assert helper_segment("cat notes.md; python3 -c 'print(1)' | tee run_analysis.py.log") is None
    assert helper_segment("./bin/python scripts/mine.py run_analysis.py") is None  # the helper as an argument


# ---- B15 and the marks route: a hidden post keeps its id and nothing else, on every surface

def test_hidden_post_identities_leave_event_frames_and_marks_are_stubs(demo):
    root, ctx = demo
    with Community(root) as board:
        post = board.rows("SELECT p.id, p.body_blob FROM post p JOIN agent a ON a.id=p.author WHERE a.kind='agent' "
                          "AND p.parent IS NULL ORDER BY p.seq")[0]
        person = _add_human(board, "v31-" + uuid.uuid4().hex[:8])
        participation.mark(board, person["id"], "post", post["id"], "checked_source", "SECRET-NOTE checked it", ())
        body = board.show(post["id"])["content"]["body"]
        participation.comment(board, person["id"], "post", post["id"], "SECRET-COMMENT really?",
                              anchor={"kind": "paragraph", "blob": post["body_blob"], "offset": 0, "length": min(20, len(body)),
                                      "quote": body[:20]})
        moderation.hide(board, "operator", post["id"], REASON)
    api = TestClient(create_app(root, local_user="local", static_dir=root / "missing"))
    log = api.get("/api/events/log", params={"limit": 1000}).json()
    frames = [e for e in log["items"] if post["id"] in json.dumps(e)] if isinstance(log, dict) else \
        [e for e in log if post["id"] in json.dumps(e)]
    assert frames, "the hidden post is mentioned by at least its publication event"
    text = json.dumps(frames)
    assert post["body_blob"] not in text and "SECRET-NOTE" not in text and "SECRET-COMMENT" not in text
    for frame in frames:
        assert frame.get("redacted") or frame.get("kind") in moderation.EVENTS, frame.get("kind")
        if frame.get("redacted"):
            assert not any(v for k, v in _walk(frame["body"]) if k in ("author", "participant", "participant_name"))
    backlog = api.get("/api/events", params={"after": 0, "once": 1}).text
    assert post["body_blob"] not in backlog and "SECRET-NOTE" not in backlog
    marks = api.get("/api/marks", params={"target_kind": "post", "target_id": post["id"]}).json()["items"]
    assert marks and all(m["hidden"] is True and m["note"] is None and m["reason"] == REASON for m in marks)
    assert "SECRET-NOTE" not in json.dumps(marks)


def _walk(value, key=None):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v, key)
    else:
        yield key, value


# ---- G5/V11 cost: the frontier read pages, the overview caps its items

def test_frontier_pages_and_overview_elides_beyond_its_cap(demo, monkeypatch):
    from daw.commons import agentview
    from daw.commons.boardservice import execute
    root, ctx = demo
    with Community(root) as board:
        whole = agentview.frontier_list(board)
        assert whole["total"] >= 2 and whole["returned"] == whole["total"] and whole["next_offset"] is None
        first = agentview.frontier_list(board, page=1)
        assert first["returned"] == 1 and first["next_offset"] == 1 and first["total"] == whole["total"]
        assert first["by_column"] == whole["by_column"]  # counts cover the whole set, not the page
        second = agentview.frontier_list(board, page=1, offset=1)
        assert second["items"][0]["id"] == whole["items"][1]["id"]
        with pytest.raises(DawError, match="invalid_frontier_page"):
            agentview.frontier_list(board, page=0)
        owner = board.one("SELECT author FROM frontier_item GROUP BY author ORDER BY count(*) DESC LIMIT 1")["author"]
        agent = board.agent(owner)
        monkeypatch.setattr(agentview, "OVERVIEW_ITEMS", 1)
        view = agentview.overview(board, agent["id"], caller=agent)
        items = [r for r in view["records"] if r["record"] == "frontier_item"]
        elided = [r for r in view["records"] if r["record"] == "frontier_items_elided"]
        assert len(items) == 1 and elided and elided[0]["total"] >= 2 and "--offset" in elided[0]["read"]
    paged = execute(root, ctx["agents"]["alice"], "frontier", {"limit": 1, "offset": 0})
    assert paged["returned"] == 1 and paged["page"] == 1


# ---- V11 discoverability: typed deliveries start with the overview too

def test_typed_prompts_start_with_the_overview(demo):
    from daw.community_runtime import TURN_START, compose_prompt
    root, ctx = demo
    with Community(root) as board:
        person = _add_human(board, "v31-" + uuid.uuid4().hex[:8])
        target = board.rows("SELECT p.id FROM post p JOIN agent a ON a.id=p.author WHERE a.kind='agent' AND p.parent IS NULL "
                            "ORDER BY p.seq")[0]["id"]
        review = participation.commission(board, person["id"], "review", ctx["agents"]["alice"], {"minutes": 15},
                                          subject_kind="post", subject_id=target, note="please review")
        asked = participation.comment(board, person["id"], "post", target, "Which samples did you exclude?", ask_author=True,
                                      budget={"minutes": 10})
        typed = [board.one("SELECT * FROM request WHERE id=?", (review["id"],)),
                 board.one("SELECT * FROM request WHERE id=?", (asked["request"]["id"],))]
        assert all(typed) and {r["task_type"] for r in typed} == {"review", "question"}
        seen = set()
        for request in typed:
            post = board.show(request["post"])
            agent = board.agent(request["target"])
            prompt = compose_prompt(board, request, agent, board.trial(agent), post, "a test", sandboxed=False)
            assert "community overview" in prompt and TURN_START in prompt, request["task_type"]
            seen.add(request["task_type"])
        assert seen


# ---- two surfaces, one record: a frontier item recorded during a turn is visible right after it

def test_frontier_items_recorded_in_a_turn_are_indexed_when_the_answer_posts(demo):
    from daw.commons import agentview
    from daw.commons.demo import deliver_scripted
    root, ctx = demo
    hook = r'''
import os, pathlib, subprocess, sys
trial = pathlib.Path(os.environ.get("HERMES_CWD") or os.getcwd())
question = sorted((trial / "workspace" / "questions").iterdir())[0].name
subprocess.run([str(trial / "bin" / "bio"), "work", "frontier", question, "--kind", "next_step",
                "--text", "V31-ITEM recompute the contrast with the paired design", "--key", "v31-next"],
               cwd=trial, check=True, capture_output=True)
'''
    with Community(root) as board:
        request = board.ask(ctx["agents"]["dana"], "operator", "Record your next step.", request_key="v31-frontier")
    deliver_scripted(root, request["id"], "Recorded.", hook=hook)
    with Community(root) as board:
        mine = agentview.frontier_list(board, author=ctx["agents"]["dana"])
        assert any("V31-ITEM" in i["text"] for i in mine["items"]) and mine["projection_current"] is True
    api = TestClient(create_app(root, local_user="local", static_dir=root / "missing"))
    assert "V31-ITEM" in api.get("/api/frontier").text


# ---- V13: a ceremony tail is not computed across a host suspension

def test_ceremony_tail_is_unavailable_across_a_suspension(tmp_path):
    from daw.commons.runmetrics import run_metrics
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "events.jsonl").write_text("")
    analysis = {"name": "terminal", "command": "./bin/python run_analysis.py x.py", "exit_code": 0, "input": {},
                "result_line": 2}
    events = [{"line": 1, "event": {"type": "tool_use", "timestamp": 1_000_000}},
              {"line": 2, "event": {"type": "tool_result", "timestamp": 1_060_000}},
              {"line": 3, "event": {"type": "result", "timestamp": 1_660_000}}]
    (folder / "execution.json").write_text(json.dumps({"wall_seconds": 660.0, "monotonic_seconds": 650.0}))
    assert run_metrics(folder, {"items": [analysis], "events": events})["minutes_after_last_successful_analysis"] == 10.0
    (folder / "execution.json").write_text(json.dumps({"wall_seconds": 660.0, "monotonic_seconds": 100.0}))
    m = run_metrics(folder, {"items": [analysis], "events": events})
    assert m["minutes_after_last_successful_analysis"] is None and m["suspended_seconds"] == 560.0
    assert any("suspension" in note for note in m["limitations"])


# ---- V18: the harness home has the learning layer off

def test_hermes_home_disables_native_memory_and_omits_the_memory_toolset(tmp_path):
    from daw import hermes
    trial = tmp_path / "agents" / "agent_x" / "trial"
    trial.mkdir(parents=True)
    hermes.prepare_home(trial, "m", "xhigh", "p")
    config = json.loads((trial / ".hermes" / "config.yaml").read_text())
    assert config["memory"]["memory_enabled"] is False and config["curator"]["enabled"] is False
    argv = hermes.command("hermes", trial, "m", "p")
    toolsets = argv[argv.index("--toolsets") + 1].split(",")
    assert "memory" not in toolsets and {"terminal", "file", "skills"} <= set(toolsets)


# ---- charter: no sandbox means no replication unless the operator allows a rehearsal

def test_unsandboxed_replication_is_refused_unless_a_rehearsal_is_allowed(tmp_path):
    root = tmp_path / "commons"
    Community.create(root).close()
    with pytest.raises(DawError, match="replication_requires_sandbox"):
        sandbox.policy(root, None, "replication")
    assert sandbox.policy(root, None, "research")["warning" if False else "config"] is None
    (root / "commons.toml").write_text("[replication]\nallow_rehearsal = false\n")
    with pytest.raises(DawError, match="replication_requires_sandbox"):
        sandbox.policy(root, None, "replication")
    (root / "commons.toml").write_text("[replication]\nallow_rehearsal = true\n")
    decision = sandbox.policy(root, None, "replication")
    assert decision["warning"].startswith("replication_unsandboxed") and decision["rehearsal_allowed_by"] == sandbox.REHEARSAL_SETTING


# ---- V13: a turn-unit context figure says what it is

def test_turn_unit_context_states_it_is_a_turn_total(tmp_path):
    from daw.commons.hygiene import context_per_call
    stream = tmp_path / "events.jsonl"
    stream.write_text(json.dumps({"type": "result", "tokens": {"input": 1000, "cache_read": 9000, "output": 10}}) + "\n")
    value = context_per_call(stream)
    assert value["unit"] == "turn" and value["max_input_tokens"] == 10000 and "not a context-window size" in value["meaning"]


# ---- round three: Codex could not write the board in local mode; verify --numbers missed linked cells

def test_unsandboxed_codex_dispatch_can_write_the_board_root(tmp_path):
    from daw import harness
    codex, hermes = harness.get("codex"), harness.get("hermes")
    argv = ["codex", "--no-daemon", "--ask-for-approval", "never", "exec", "--json", "--sandbox", "workspace-write", "-"]
    board = tmp_path / "board"
    board.mkdir()
    out = codex.local_board_access(argv, board)
    assert out[out.index("exec") + 1:out.index("exec") + 3] == ["--add-dir", str(board.resolve())]
    assert codex.local_board_access(out, board) == out  # idempotent
    assert hermes.local_board_access(argv, board) == argv  # no sandbox of its own
    decision = {"config": None, "override": None, "tenancy": "local"}
    wrapped, _, _ = sandbox.apply(decision, argv, {}, trial=tmp_path, board_root=board, adapter=codex,
                                  agent_config={}, run="run_x")
    assert "--add-dir" in wrapped


def test_verify_numbers_checks_the_pointer_at_each_number_and_linked_tables(tmp_path):
    from daw.artifacts import register_artifact
    from daw.catalog import Workspace
    from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
    from daw.work import create_question
    board = Community.create(tmp_path / "community")
    (board.library.root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")
    board.library.close()
    from daw.catalog import Workspace as W
    board.library = W(board.root / "library")
    root = tmp_path / "ws"
    Workspace.create(root).close()
    (root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")
    ws = Workspace(root)
    try:
        q = create_question(ws, "linked cells")["question"]
        src = tmp_path / "in.tsv"
        src.write_text("x\n1\n")
        asset = ws.local_asset(src, "input")
        code = ws.put_bytes(b"# analysis\n")
        out = tmp_path / "contrast.tsv"
        out.write_text("contrast\tlog2FC\ncAMP_vs_vehicle\t0.8389319311268126\nother\t1.883111717902116\n")
        spec = ArtifactRegistration(title="contrast", summary="s", derivation=Derivation(
            inputs=[ObjectInput(blob=asset["blob"], source_identity=asset["asset_revision"])], code=[code],
            parameters={}, references=[], environment={"t": True}))
        aid = register_artifact(ws, out, spec, question=q)["artifact"]
        board.publish("operator", "Tables", "The contrast table.", workspace=root, artifacts=[aid], question=q)
        # The answer cites cells of a table it does not itself attach (round three's false "unmatched").
        good = board.publish("operator", "Answer",
                             f"The response difference is [0.84]({aid}#row=cAMP_vs_vehicle;col=log2FC;round=2), "
                             f"and the other value is 1.883.")
        result = board.verify(good["id"], numbers=True)
        numbers = result["numbers"]
        assert numbers["matched_by_pointer"] == 1 and numbers["unmatched"] == [] and numbers["pointer_mismatches"] == []
        assert [t["source"] for t in numbers["tables"]] == ["linked"] and result["verified"]
        wrong = board.publish("operator", "Wrong", f"The difference is [0.91]({aid}#row=cAMP_vs_vehicle;col=log2FC;round=2).")
        bad = board.verify(wrong["id"], numbers=True)
        assert [m["number"] for m in bad["numbers"]["pointer_mismatches"]] == ["0.91"] and bad["verified"] is False
    finally:
        ws.close()
        board.close()
