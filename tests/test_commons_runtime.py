"""Runtime area (M3.3–M3.6): harness adapters, task types, budgets and clocks, delivery rules, sandbox."""
import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

from daw import agent_capture, harness
from daw.commons import budgets, egress, sandbox, tasks
from daw.commons.assignments import assign, cohort_run, collect_cohorts
from daw.commons.demo import scripted_runtime
from daw.commons.participants import add_participant
from daw.community import Community
from daw.community_runtime import add_agent, assignment_prompt, dispatch, fork_agent
from daw.community_service import expire_overdue, pending_deliveries
from daw.harness import claude, codex, mcp, mcp_server, scripted
from daw.util import DawError, now, read_json

def events(board, kind):
    return [json.loads(r["body"]) for r in board.rows("SELECT body FROM event WHERE kind=? ORDER BY seq", (kind,))]


def answer_for(answers, request, board, text):
    (answers / f"{board.one('SELECT post FROM request WHERE id=?', (request['id'],))['post']}.md").write_text(text)


def comment(board, author, parent, body, target):
    """A person's anchored comment that asks the target's author (the participation area's record shape)."""
    with board.writer(), board.library.writer():
        post = board._post(author, "Comment", body, parent=parent, kind="comment",
                           evidence={"target_kind": "post", "target_id": parent, "ask_author": True,
                                     "anchor": {"kind": "paragraph", "offset": 0, "length": 12, "quote": "log2 ratio"}})
        identity = "request_" + uuid.uuid4().hex
        with board.db:
            board.db.execute("INSERT INTO request(id,post,target,state,active_run,answer,created,updated) "
                             "VALUES(?,?,?,'pending',NULL,NULL,?,?)", (identity, post, target, now(), now()))
    return board.one("SELECT * FROM request WHERE id=?", (identity,))


# ---- M3.3 adapters ------------------------------------------------------------------------------

def test_registry_and_legacy_hermes_prompt_is_byte_identical():
    assert [harness.get(n).name for n in harness.NAMES] == list(harness.NAMES)
    assert harness.for_agent({"config": {}}).name == "hermes"
    with pytest.raises(DawError, match="unknown_harness"):
        harness.get("copilot")
    post = {"id": "post_123", "parent": None, "content": {"body": "Body"}}
    trial = Path("/x/agents/agent_abc/trial")
    # Frozen digests of the pre-adapter assignment prompt (question and answer notification).
    assert hashlib.sha256(assignment_prompt("agent_abc", trial, post).encode()).hexdigest() == \
        "202c1b97fdde02cac89b77d9347c4eea3ba7aedf79db4ad68977a40af7fa7e12"
    assert hashlib.sha256(assignment_prompt("agent_abc", trial, post, notification=True).encode()).hexdigest() == \
        "371f700ecf9f10dfef009fe03beaa69e4f52c115fcfcfe39bd6f435b08012dce"


def test_codex_command_is_the_evaluator_launch_line_and_resumes_persistently(tmp_path):
    from benchmarks.agent.runner import codex_command as evaluator
    assert evaluator is codex.codex_command
    argv = codex.codex_command("codex", tmp_path, tmp_path / "final.md")
    assert argv[:7] == ["codex", "--no-daemon", "--ask-for-approval", "never", "exec", "--json", "--ephemeral"]
    config = {"model": "m", "effort": "high", "public": False}
    resumed = codex.ADAPTER.command("codex", tmp_path, config, resume="thread-1")
    assert "--ephemeral" not in resumed and resumed[-3:] == ["resume", "thread-1", "-"]
    assert "--output-last-message" not in resumed
    with pytest.raises(DawError, match="harness_fork_unsupported"):
        codex.ADAPTER.command("codex", tmp_path, config, resume="t", fork=True)
    assert codex.ADAPTER.environment({"HERMES_HOME": "x"}, tmp_path)["CODEX_HOME"] == str(tmp_path / ".codex")


def test_claude_settings_confine_file_tools_and_command_resumes_or_forks(tmp_path):
    trial = tmp_path / "agents/a/trial"
    (trial / ".agents/skills/bio-research").mkdir(parents=True)
    (trial / ".agents/skills/bio-research/SKILL.md").write_text("skill")
    config = {"model": "opus", "effort": "xhigh", "public": False, "harness": "claude"}
    runtime = claude.ADAPTER.prepare(trial, config)
    home = trial / ".claude-home"
    settings = read_json(home / "settings.json")
    assert settings["permissions"]["defaultMode"] == "dontAsk" and settings["cleanupPeriodDays"] >= 36500
    assert f"Edit(//{str(trial).lstrip('/')}/**)" in settings["permissions"]["allow"]
    assert f"Edit(//{str(trial).lstrip('/')}/src/**)" in settings["permissions"]["deny"]
    assert "WebFetch" not in settings["permissions"]["allow"]
    assert (home / "skills/bio-research/SKILL.md").read_text() == "skill" and runtime["harness"] == "claude"
    argv = claude.ADAPTER.command("claude", trial, config, resume="s1", fork=True)
    assert argv[:5] == ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    assert argv[argv.index("--setting-sources") + 1] == "user" and argv[-3:] == ["--resume", "s1", "--fork-session"]
    assert argv[argv.index("--tools") + 1] == "Bash,Read,Edit,Write,Glob,Grep"
    env = claude.ADAPTER.environment({"HERMES_X": "1", "ANTHROPIC_API_KEY": "k"}, trial)
    assert env["CLAUDE_CONFIG_DIR"] == str(home) and "HERMES_X" not in env and env["ANTHROPIC_API_KEY"] == "k"


def test_stream_parsers_share_one_shape_and_report_missing_telemetry_as_unavailable(tmp_path):
    lines = [{"type": "system", "subtype": "init", "session_id": "s"},
             {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                            "input": {"command": "./bin/bio search"}},
                                                           {"type": "tool_use", "id": "t2", "name": "Write",
                                                            "input": {"file_path": "scripts/a.py"}}]}},
             {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x",
                                                       "is_error": True}]}},
             {"type": "result", "subtype": "success", "is_error": False, "result": "done", "session_id": "s"}]
    path = tmp_path / "claude.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    parsed = claude.parse(path)
    shell, write, final = parsed["items"]
    assert shell["name"] == "terminal" and shell["command"] == "./bin/bio search" and shell["exit_code"] == 1
    assert write["name"] == "write_file" and write["input"]["path"] == "scripts/a.py" and write["exit_code"] is None
    assert final == {"line": 4, "type": "agent_message", "text": "done"}
    assert parsed["turns_completed"] == 1 and parsed["malformed_lines"] == [5] and parsed["thread_ids"] == ["s", "s"]
    assert parsed["usage"]["input_tokens"] is None  # not reported: unavailable, never zero
    jsonl = tmp_path / "mcp.jsonl"
    jsonl.write_text("\n".join(json.dumps(x) for x in [
        {"type": "session", "id": "n1"}, {"type": "tool_call", "id": "c", "name": "shell", "input": {"command": "ls"}},
        {"type": "tool_result", "id": "c", "output": "", "exit_code": 0}, {"type": "future_event"},
        {"type": "message", "text": "answer"}, {"type": "turn_completed", "usage": {"input_tokens": 3, "output_tokens": 2}}]))
    parsed = mcp.parse(jsonl)
    assert parsed["items"][0]["name"] == "terminal" and parsed["items"][0]["exit_code"] == 0
    assert parsed["turns_completed"] == 1 and not parsed["malformed_lines"]
    assert parsed["usage"]["input_tokens"] == 3 and parsed["usage"]["cached_input_tokens"] is None


def test_mcp_harness_options_are_validated_templates(tmp_path):
    options = {"executable": "agent", "args": ["--mcp", "{mcp_config}", "--model", "{model}"],
               "resume_args": ["--resume", "{session}"]}
    config = {"model": "m", "effort": "e", "provider": "p", "harness_options": options}
    trial = tmp_path / "trial"
    trial.mkdir()
    mcp.ADAPTER.prepare(trial, config)
    server = read_json(trial / ".mcp-home/mcp.json")["mcpServers"]["bio"]
    assert server["args"] == ["mcp", "serve"] and server["command"] == str(trial / "bin/bio")
    argv = mcp.ADAPTER.command(None, trial, config, resume="s; rm -rf /")
    assert argv == ["agent", "--mcp", str(trial / ".mcp-home/mcp.json"), "--model", "m", "--resume", "s; rm -rf /"]
    for bad in ({"args": ["{secret}"]}, {"resume_args": ["--resume"]}, {"args": "x"}, {"shell": True}):
        with pytest.raises(DawError, match="invalid_harness_options"):
            mcp.check_options(bad)
    assert not mcp.ADAPTER.resumable({"harness_options": {"executable": "agent"}})


def test_mcp_server_exposes_agent_safe_tools_inside_the_checkout(demo):
    root, ctx = demo
    with Community(root) as board:
        trial = board.trial(board.agent("dana"))
    checkout = mcp_server.Checkout(trial, env={})
    assert checkout.env["BIO_AGENT"] == ctx["agents"]["dana"] and checkout.env["BIO_COMMUNITY"] == str(root)
    with pytest.raises(DawError, match="agent_identity_mismatch"):
        mcp_server.Checkout(trial, env={"BIO_AGENT": "agent_other"})
    init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, checkout)
    assert init["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, checkout) is None
    names = {t["name"] for t in mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, checkout)["result"]["tools"]}
    assert {"search", "register", "sync", "gap", "community_publish", "community_inbox", "community_verify"} <= names
    assert not {n for n in names if any(word in n for word in ("run", "serve", "retry", "recover", "dispatch"))}
    call = mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                              "params": {"name": "community_show", "arguments": {"post": ctx["posts"]["finding"]}}}, checkout)
    assert not call["result"]["isError"] and json.loads(call["result"]["content"][0]["text"])["id"] == ctx["posts"]["finding"]
    outside = mcp_server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                 "params": {"name": "register", "arguments": {"path": "../../../../etc/passwd"}}}, checkout)
    assert outside["result"]["isError"] and "path_outside_checkout" in outside["result"]["content"][0]["text"]
    bad = mcp_server.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                             "params": {"name": "community_inbox", "arguments": {"sent": "yes"}}}, checkout)
    assert bad["result"]["isError"]
    assert mcp_server.handle({"jsonrpc": "2.0", "id": 6, "method": "nope"}, checkout)["error"]["code"] == -32601


# ---- Dispatch through every adapter (scripted stand-in executables) -----------------------------

@pytest.mark.parametrize("name,options", [("claude", None), ("codex", None), ("scripted", {"stream_format": "jsonl"}),
                                          ("scripted", {"stream_format": "claude"})])
def test_dispatch_resumes_native_sessions_through_each_adapter(demo, name, options):
    root, _ = demo
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        agent = add_agent(board, "erin", model="test-model", harness=name, harness_options=options)
        assert agent["config"]["harness"] == name
        first = board.ask("erin", "operator", "First assignment")
        answer_for(answers, first, board, "Turn {turns}: finding with pointers.")
        done = dispatch(board, first["id"], executable)
        assert done["state"] == "completed" and board.show(done["answer"])["content"]["body"] == "Turn 1: finding with pointers."
        session = board.agent("erin")["native_session"]
        assert session
        follow = board.ask("erin", "operator", "Second assignment")
        answer_for(answers, follow, board, "Turn {turns}: resumed.")
        assert board.show(dispatch(board, follow["id"], executable)["answer"])["content"]["body"] == "Turn 2: resumed."
        assert board.agent("erin")["native_session"] == session
        run = board.root / board.one("SELECT path FROM attempt WHERE request=?", (follow["id"],))["path"]
        receipt = read_json(run / "state-receipt.json")
        assert receipt["harness"] == name and receipt["session"] == session
        assert {"harness": name} == {k: v for k, v in events(board, "delivery_started")[-1].items() if k == "harness"}
        if name == "codex":  # no native branch: workspace forks only
            with pytest.raises(DawError, match="harness_fork_unsupported"):
                fork_agent(board, "erin", "erin-branch", inherit_conversation=True)
            assert fork_agent(board, "erin", "erin-copy")["config"]["harness"] == "codex"


def test_claude_conversation_fork_branches_on_launch(demo):
    root, _ = demo
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        add_agent(board, "cara", harness="claude")
        dispatch(board, board.ask("cara", "operator", "Start")["id"], executable)
        parent = board.agent("cara")
        child = fork_agent(board, "cara", "cara-branch", inherit_conversation=True)
        assert child["config"]["harness"] == "claude" and child["config"]["fork_pending"]
        request = board.ask("cara-branch", "operator", "Branch")
        answer_for(answers, request, board, "Turn {turns}")
        done = dispatch(board, request["id"], executable)
        run = board.root / board.one("SELECT path FROM attempt WHERE request=?", (request["id"],))["path"]
        assert "--fork-session" in read_json(run / "execution.json")["argv"]
        assert board.show(done["answer"])["content"]["body"] == "Turn 2"
        assert board.agent("cara-branch")["native_session"] != parent["native_session"]
        with pytest.raises(DawError, match="harness_mismatch"):
            add_agent(board, "x", harness="codex", parent=parent["id"])


# ---- Service delivery rules ---------------------------------------------------------------------

def test_service_delivers_comments_and_person_authorized_tasks_but_never_notices(demo):
    from daw.commons.notices import notify
    root, ctx = demo
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        rhea = add_participant(board, "rhea", "human")
        fresh = add_agent(board, "fresh")
        alice = ctx["agents"]["alice"]
        note = notify(board, "watcher", alice, "New evidence", "An accession appeared.", key="n")
        human_comment = comment(board, rhea["id"], ctx["posts"]["finding"], "Is this paired?", alice)
        unstarted_comment = comment(board, rhea["id"], ctx["posts"]["finding"], "And here?", fresh["id"])
        promoted = assign(board, "operator", fresh["id"], "Scout", "Find knockdown data.", task_type="scouting",
                          budget={"minutes": 5})
        late = assign(board, "operator", ctx["agents"]["dana"], "Late", "Too late.", task_type="digest",
                      deadline="2020-01-01T00:00:00+00:00")
        selected = {r["id"] for r in pending_deliveries(board)}
        assert human_comment["id"] in selected and promoted["id"] in selected
        assert not selected & {note["id"], unstarted_comment["id"], late["id"]}
        assert expire_overdue(board) == [late["id"]]
        assert board.one("SELECT state FROM request WHERE id=?", (late["id"],))["state"] == "failed"
        assert events(board, "deadline_passed")[-1]["request"] == late["id"]
        with pytest.raises(DawError, match="notice_not_deliverable"):
            dispatch(board, note["id"], executable)
        answer_for(answers, human_comment, board, "Donors are unrecorded; pairing cannot be assumed.")
        done = dispatch(board, human_comment["id"], executable)
        assert board.show(done["answer"])["content"]["parent"] == human_comment["post"]
        prompt = (board.root / board.one("SELECT path FROM attempt WHERE request=?", (human_comment["id"],))["path"]
                  / "prompt.txt").read_text()
        assert "COMMENT by human participant rhea" in prompt and '"log2 ratio"' in prompt


def test_expired_deadline_is_refused_at_dispatch(demo):
    root, ctx = demo
    with Community(root) as board, scripted_runtime(root) as (executable, _):
        late = assign(board, "operator", ctx["agents"]["bob"], "Late", "x", task_type="review",
                      deadline="2020-01-01T00:00:00+00:00")
        with pytest.raises(DawError, match="deadline_passed"):
            dispatch(board, late["id"], executable)
        assert board.one("SELECT state FROM request WHERE id=?", (late["id"],))["state"] == "failed"
        assert not board.rows("SELECT id FROM attempt WHERE request=?", (late["id"],))
    with Community(root) as board:
        with pytest.raises(DawError, match="permission_denied"):
            assign(board, ctx["agents"]["bob"], ctx["agents"]["alice"], "t", "b")


# ---- M3.4 task types and M3.5 budgets -----------------------------------------------------------

def _run_folder(board, request):
    return board.root / board.one("SELECT path FROM attempt WHERE request=?", (request["id"],))["path"]


def test_typed_research_prompt_budget_and_outcome(demo):
    root, ctx = demo
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        request = assign(board, "operator", ctx["agents"]["bob"], "Robustness", "Check the contrast.",
                         budget={"minutes": 30, "tokens": 1000, "download_bytes": 4096},
                         deadline="2099-01-01T00:00:00+00:00")
        answer_for(answers, request, board, f"Finding cites {ctx['artifacts']['normalized']} and post_{'0' * 32}.")
        hook = answers / f"{request['post']}.hook.py"
        hook.write_text("import os, shutil\nshutil.copy('workspace/config.toml', 'config-during-task.toml')\n")
        config_before = (board.trial(board.agent("bob")) / "workspace/config.toml").read_bytes()
        dispatch(board, request["id"], executable)
        folder = _run_folder(board, request)
        prompt = (folder / "prompt.txt").read_text()
        assert prompt.startswith("You are a researcher") and "TASK TYPE: research" in prompt
        assert "30 minutes" in prompt and "Deadline: 2099-01-01T00:00:00+00:00" in prompt
        assert read_json(folder / "execution.json")["timeout_seconds"] == 1800
        trial = board.trial(board.agent("bob"))
        during = (trial / "config-during-task.toml").read_text()
        assert "bundle_bytes = 4096" in during and "asset_bytes = 4096" in during
        assert (trial / "workspace/config.toml").read_bytes() == config_before
        receipt = read_json(folder / "budget.json")
        assert receipt["download_bytes"]["restored"] and receipt["download_bytes"]["applied"]["bundle_bytes"] == 4096
        # The demo's Hermes-shaped stream carries no native token fields: unavailable, never zero.
        assert receipt["tokens"]["used"] == "unavailable" and receipt["tokens"]["exceeded"] is None
        [outcome] = events(board, "task_outcome")
        assert outcome["task_type"] == "research" and outcome["request"] == request["id"]
        assert outcome["criteria"]["pointers"]["unresolved"] == [f"post_{'0' * 32}"]
        assert ctx["artifacts"]["normalized"] not in outcome["criteria"]["pointers"]["unresolved"]
        assert outcome["criteria"]["budget"]["tokens"]["used"] == "unavailable"
        assert board.show(board.one("SELECT answer FROM request WHERE id=?", (request["id"],))["answer"])["content"][
            "evidence"]["task_type"] == "research"


def test_review_deliverable_is_validated_structurally(demo):
    root, ctx = demo
    finding = ctx["posts"]["finding"]
    review = {"review": {"target": finding, "verdicts": [
        {"criterion": "limitations_stated", "verdict": "supported", "pointers": [finding], "note": "stated"},
        {"criterion": "scope_matches_evidence", "verdict": "partially_supported", "pointers": [], "note": "n=4"}]}}
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        request = assign(board, "operator", ctx["agents"]["bob"], "Review", "Review the finding.", task_type="review",
                         evidence={"subject_kind": "post", "subject_id": finding,
                                   "criteria": ["limitations_stated", "scope_matches_evidence", "methods_reproducible"]})
        answer_for(answers, request, board, "Review below.\n```review\n" + json.dumps(review) + "\n```\n")
        dispatch(board, request["id"], executable)
        prompt = (_run_folder(board, request) / "prompt.txt").read_text()
        assert "This is a REVIEW task" in prompt and f"Subject: post {finding}." in prompt
        assert "Criteria: limitations_stated, scope_matches_evidence, methods_reproducible." in prompt
        check = events(board, "task_outcome")[-1]["criteria"]["review"]
        assert not check["valid"] and check["criteria_missing"] == ["methods_reproducible"]
        assert check["verdicts_without_pointers"] == ["scope_matches_evidence"] and check["target_resolves"]
        assert not [f for f in events(board, "task_outcome")[-1]["deliverables_found"] if f.startswith("review:")]
        complete = assign(board, "operator", ctx["agents"]["bob"], "Review", "Review again.", task_type="review",
                          evidence={"subject_id": finding, "criteria": ["limitations_stated"]})
        answer_for(answers, complete, board, "```json\n" + json.dumps({"review": {"target": finding, "verdicts": [
            review["review"]["verdicts"][0]]}}) + "\n```")
        dispatch(board, complete["id"], executable)
        outcome = events(board, "task_outcome")[-1]
        assert outcome["criteria"]["review"]["valid"] and "review:answer_block" in outcome["deliverables_found"]
    value, problems = tasks.review_block("```review\n{bad\n```")
    assert value is None and "invalid JSON" in problems[0]


REPLICATE = '''import os
from daw.artifacts import artifact_info, register_artifact
from daw.catalog import Workspace
from daw.substrate_models import ArtifactRegistration, Derivation
from daw.work import create_question
ws = Workspace(os.environ["BIO_WORKSPACE"])
with ws.writer():
    manifest = artifact_info(ws, "{original}")["manifest"]
    question = create_question(ws, "Replicate {original}")["question"]
    out = "replicated.tsv"
    open(out, "w").write({content!r})
    register_artifact(ws, out, ArtifactRegistration(title="Replication", summary="re-executed",
        output_role=manifest["output_role"], derivation=Derivation(**manifest["derivation"])), question=question)
ws.close()
'''


@pytest.mark.parametrize("identical", [True, False])
def test_replication_compares_bytes_and_requires_a_correction(demo, identical):
    root, ctx = demo
    original = ctx["artifacts"]["contrast"]
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        target = board.agent("alice-fork")
        content = (board.library.blob_path(board.library.one("SELECT output_blob FROM artifact WHERE id=?",
                                                             (original,))["output_blob"]).read_text()
                   if identical else "contrast\tlog2_ratio\nB_vs_A\t1.60\n")
        request = assign(board, "operator", target["id"], "Replicate", "Replicate the contrast.", task_type="replication",
                         evidence={"subject_kind": "artifact", "subject_id": original})
        (answers / f"{request['post']}.hook.py").write_text(REPLICATE.format(original=original, content=content))
        dispatch(board, request["id"], executable)
        [result] = events(board, "task_outcome")[-1]["criteria"]["replication"]
        if identical:
            assert result["outcome"] == "byte_identical" and result["identical"] == [original]
            assert not events(board, "notice_queued")
        else:
            assert result["outcome"] == "bytes_differ" and result["correction_required"] and not result["correction_post"]
            notice = events(board, "notice_queued")[-1]
            assert notice["target"] == ctx["agents"]["alice"]
            shown = board.show(notice["post"])
            assert shown["parent"] == ctx["posts"]["finding"] and result["different"][0] in shown["content"]["body"]


def test_scouting_flags_analysis_and_writing_requires_pointers(demo):
    root, ctx = demo
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        scout = assign(board, "operator", ctx["agents"]["dana"], "Scout", "Find data.", task_type="scouting")
        dispatch(board, scout["id"], executable)
        criteria = events(board, "task_outcome")[-1]["criteria"]
        assert criteria["analysis_out_of_scope"] and criteria["analysis_receipts"] == 2 and criteria["analysis_failures"] == 1
        write = assign(board, "operator", ctx["agents"]["dana"], "Write", "Write it up.", task_type="writing")
        answer_for(answers, write, board, "The marker rose a lot (no pointers).")
        dispatch(board, write["id"], executable)
        outcome = events(board, "task_outcome")[-1]
        assert outcome["deliverables_found"] == [] and outcome["criteria"]["cites_records"] is False
        digest = assign(board, "operator", ctx["agents"]["dana"], "Digest", "Digest the week.", task_type="digest")
        answer_for(answers, digest, board, f"Correction {ctx['posts']['correction']} superseded {ctx['posts']['finding']}.")
        dispatch(board, digest["id"], executable)
        outcome = events(board, "task_outcome")[-1]
        assert outcome["criteria"]["cites_records"] and outcome["deliverables_found"]


def test_token_report_and_execution_timeout():
    assert budgets.execution_timeout(0, {"minutes": 2}) == 120 and budgets.execution_timeout(60, {"minutes": 2}) == 60
    assert budgets.execution_timeout(0, {}) == 0
    assert budgets.token_report({"tokens": 10}, None)["used"] == "unavailable"
    assert budgets.token_report({"tokens": 10}, {"input_tokens": 0, "output_tokens": 0})["used"] == "unavailable"
    report = budgets.token_report({"tokens": 10}, {"input_tokens": 8, "output_tokens": 5})
    assert report["used"] == 13 and report["exceeded"] is True
    assert budgets.dump_toml({"budgets": {"a": 1, "b": 0.5}, "x": "q\"s"}) == 'x = "q\\"s"\n\n[budgets]\na = 1\nb = 0.5\n'


# ---- M3.5 clocks: stall and host sleep ----------------------------------------------------------

def test_stall_is_reported_to_the_operator_without_killing(demo):
    root, ctx = demo
    with Community(root) as board, scripted_runtime(root) as (executable, _):
        trial = board.trial(board.agent("bob"))
        (trial / "scripted-sleep").write_text("1.5")
        request = board.ask("bob", ctx["agents"]["alice"], "Slow question")
        done = dispatch(board, request["id"], executable, stall_minutes=0.5 / 60)
        assert done["state"] == "completed"
        folder = _run_folder(board, request)
        assert read_json(folder / "stall.json")["episode"] == 1
        assert read_json(folder / "execution.json")["stalls"][0]["action"].startswith("reported")
        assert events(board, "delivery_stalled")[-1]["run"] == done["active_run"]
        notice = board.one("SELECT * FROM request WHERE task_type='notice' ORDER BY created DESC LIMIT 1")
        assert notice["target"] == "operator" and board.agent(board.show(notice["post"])["author"])["name"] == "runtime"
        assert notice["id"] not in {r["id"] for r in pending_deliveries(board)}
        stalled = board.ask("bob", ctx["agents"]["alice"], "Stopped question")
        with pytest.raises(DawError, match="agent_delivery_failed"):
            dispatch(board, stalled["id"], executable, stall_minutes=0, stall_timeout=1)
        execution = read_json(_run_folder(board, stalled) / "execution.json")
        assert execution["state"] == "stalled" and "operator stall timeout" in execution["stop_reason"]


def test_host_sleep_is_detected_from_wall_minus_monotonic(tmp_path, monkeypatch):
    class Clock:
        offset = 0.0

        def monotonic(self):
            import time
            return time.monotonic()

        def time(self):
            import time
            self.offset += 100
            return time.time() + self.offset

        def sleep(self, seconds):
            import time
            time.sleep(seconds)
    monkeypatch.setattr(agent_capture, "time", Clock())
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("")
    result = agent_capture.execute([sys.executable, "-c", "import time; time.sleep(0.3)"], prompt, tmp_path, tmp_path,
                                   {"PATH": "/usr/bin:/bin"})
    assert result["host_sleep_detected"] and result["suspended_seconds"] > 60
    quiet = tmp_path / "quiet"
    quiet.mkdir()
    monkeypatch.undo()
    normal = agent_capture.execute([sys.executable, "-c", "pass"], prompt, quiet, tmp_path, {"PATH": "/usr/bin:/bin"})
    assert "host_sleep_detected" not in normal and "stalls" not in normal


# ---- M3.6 sandbox and egress --------------------------------------------------------------------

def test_container_argv_mounts_platform_read_only_and_passes_secrets_by_name(tmp_path):
    root = tmp_path / "commons"
    trial = root / "agents/agent_a/trial"
    for part in ("src/daw", ".agents/skills", "bin", ".claude-home", "workspace"):
        (trial / part).mkdir(parents=True)
    (root / "runs").mkdir()
    auth = tmp_path / "creds.json"
    auth.write_text("{}")
    (root / "sandbox.toml").write_text('engine = "podman"\nimage = "agent:1"\nnetwork = "egress-net"\n'
                                       'proxy = "http://egress:3128"\nenv = ["ANTHROPIC_API_KEY"]\nscratch_bytes = 1048576\n')
    config = sandbox.load(root)
    env = {"ANTHROPIC_API_KEY": "secret", "AWS_SECRET_ACCESS_KEY": "host", "BIO_AGENT": "agent_a",
           "CLAUDE_CONFIG_DIR": str(trial / ".claude-home"), "BIO_CLAUDE_AUTH_FILE": str(auth), "PATH": "/usr/bin"}
    argv, client = sandbox.container_argv(config, ["claude", "-p"], env, trial=trial, board_root=root,
                                          auth_files=claude.ADAPTER.auth_files(env), name="colloquy-run_1")
    assert argv[:3] == ["podman", "run", "--rm"] and argv[-3:] == ["agent:1", "claude", "-p"]
    assert "secret" not in " ".join(argv) and client["ANTHROPIC_API_KEY"] == "secret"
    assert "AWS_SECRET_ACCESS_KEY" not in client and "AWS_SECRET_ACCESS_KEY" not in argv
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "--mount"]
    assert f"type=bind,src={trial},dst={trial}" in mounts
    assert f"type=bind,src={trial / 'src'},dst={trial / 'src'},readonly" in mounts
    assert f"type=bind,src={trial / '.agents'},dst={trial / '.agents'},readonly" in mounts
    assert f"type=tmpfs,dst={root / 'agents'},tmpfs-size=65536" in mounts and f"type=tmpfs,dst={root / 'runs'},tmpfs-size=65536" in mounts
    assert f"type=bind,src={auth},dst={auth},readonly" in mounts
    assert argv[argv.index("--network") + 1] == "egress-net" and "--read-only" in argv and "ALL" in argv
    assert "/tmp:rw,size=1048576,mode=1777" in argv and client["HTTPS_PROXY"] == "http://egress:3128"
    assert "api.anthropic.com" in sandbox.hosts(config, claude.ADAPTER.hosts({})) and "zenodo.org" in sandbox.hosts(None)
    (root / "sandbox.toml").write_text('engine = "lxc"\n')
    with pytest.raises(DawError, match="invalid_sandbox_config"):
        sandbox.load(root)


def test_multi_tenant_dispatch_requires_a_sandbox_or_a_recorded_override(demo):
    root, ctx = demo
    sandbox.record_tenancy(root, "accounts")
    sandbox.record_tenancy(root, "local")
    assert sandbox.tenancy(root) == "accounts"  # sticky
    with Community(root) as board, scripted_runtime(root) as (executable, _):
        request = board.ask("bob", ctx["agents"]["alice"], "Question")
        with pytest.raises(DawError, match="sandbox_required"):
            dispatch(board, request["id"], executable)
        assert board.one("SELECT state FROM request WHERE id=?", (request["id"],))["state"] == "pending"
        with pytest.raises(DawError, match="override_reason_required"):
            dispatch(board, request["id"], executable, allow_unsandboxed=" ")
        done = dispatch(board, request["id"], executable, allow_unsandboxed="single trusted operator during pilot")
        assert read_json(_run_folder(board, request) / "sandbox.json")["override"].startswith("single trusted")
        assert events(board, "sandbox_override")[-1]["request"] == done["id"]
        # A configured sandbox wraps the harness argv in the container engine.
        (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\n')
        wrapped = board.ask("bob", ctx["agents"]["alice"], "Contained")
        with pytest.raises(DawError, match="agent_delivery_failed"):
            dispatch(board, wrapped["id"], executable)  # no container engine in the offline test environment
        receipt = read_json(_run_folder(board, wrapped) / "sandbox.json")
        assert receipt["sandboxed"] and receipt["network"] == "none" and receipt["harness_argv"][0] == executable
        assert read_json(_run_folder(board, wrapped) / "execution.json")["argv"][:2] == ["docker", "run"]


def test_egress_proxy_allows_listed_hosts_and_denies_others_on_local_sockets(tmp_path):
    log = tmp_path / "egress.jsonl"

    async def scenario():
        async def echo(reader, writer):
            writer.write(b"upstream:" + await reader.read(5))
            await writer.drain()
            writer.close()
        upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
        port = upstream.sockets[0].getsockname()[1]
        policy = egress.Policy(["data.test"], ports=(port,), allow_private=True,
                               resolver=lambda host, p: ["127.0.0.1"])
        proxy = await egress.start(policy, "127.0.0.1", 0, log)
        proxy_port = proxy.sockets[0].getsockname()[1]

        async def connect(target):
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
            writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
            await writer.drain()
            status = (await reader.readuntil(b"\r\n\r\n")).split(b"\r\n")[0]
            body = b""
            if b" 200 " in status:
                writer.write(b"hello")
                await writer.drain()
                body = await reader.read(100)
            writer.close()
            return status, body
        allowed = await connect(f"api.data.test:{port}")
        denied = await connect("evil.example:443")
        wrong_port = await connect(f"data.test:{port + 1 if port < 65535 else port - 1}")
        proxy.close()
        upstream.close()
        return allowed, denied, wrong_port
    allowed, denied, wrong_port = asyncio.run(scenario())
    assert b" 200 " in allowed[0] and allowed[1] == b"upstream:hello"
    assert b" 403 " in denied[0] and b" 403 " in wrong_port[0]
    decisions = [json.loads(line) for line in log.read_text().splitlines()]
    assert {d["reason"] for d in decisions} >= {"allowed", "host_not_allowlisted", "port_not_allowed"}
    private = egress.Policy(["data.test"], resolver=lambda host, p: ["10.0.0.5"])
    assert private.check("data.test", 443) == (False, "resolves_to_private_address", None)
    assert egress.Policy().check("notzenodo.org", 443)[1] == "host_not_allowlisted"
    method, host, port, head = egress.parse_head(b"GET http://www.ebi.ac.uk/x?y=1 HTTP/1.1\r\nHost: www.ebi.ac.uk\r\n\r\n")
    assert (method, host, port) == ("GET", "www.ebi.ac.uk", 80) and head.startswith(b"GET /x?y=1 HTTP/1.1\r\n")


# ---- Milestone 5: the same assignments on two harnesses -----------------------------------------

def test_cohort_run_compares_the_same_assignments_on_two_harnesses(demo):
    from daw.commons.archive import Archive
    from daw.commons.metrics import compare
    root, _ = demo
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        add_agent(board, "hermes-one")
        add_agent(board, "claude-one", harness="claude", model="claude-test")
        assignments = [(f"Assignment {n}", f"Assignment {n}: investigate fixture marker {n}.") for n in range(3)]
        queued = cohort_run(board, "operator", "m5", assignments, ["hermes-one", "claude-one"], budget={"minutes": 10})
        selected = {r["id"] for r in pending_deliveries(board)}
        assert len(queued) == 2 and all(len(v) == 3 for v in queued.values())
        assert len(selected & {r for v in queued.values() for r in v.values()}) == 2  # one per idle agent
        for requests in queued.values():
            for request in requests.values():
                assert dispatch(board, request, executable)["state"] == "completed"
        cohorts = collect_cohorts(board, "operator", "m5")
        assert cohort_run(board, "operator", "m5", assignments, ["hermes-one"]) == {
            board.agent("hermes-one")["id"]: queued[board.agent("hermes-one")["id"]]}  # idempotent
    with Archive(root) as view:
        value = compare(view, list(cohorts.values()))
    assert sorted(h for c in value["cohorts"] for h in c["harnesses"]) == ["claude", "hermes"]
    assert value["shared_assignments"] == 3
    with pytest.raises(DawError, match="unknown_cohort_run"), Community(root) as board:
        collect_cohorts(board, "operator", "missing")


def test_cli_add_agent_harness_and_agents_listing(demo):
    from typer.testing import CliRunner

    from daw.bio_cli import app
    root, _ = demo
    runner = CliRunner()
    result = runner.invoke(app, ["community", "--root", str(root), "add-agent", "cli-claude", "--harness", "claude"])
    assert result.exit_code == 0, result.output
    created = json.loads(result.output)
    assert created["config"]["harness"] == "claude" and created["config"]["model"] == "opus"
    listing = json.loads(runner.invoke(app, ["community", "--root", str(root), "agents"]).output)
    assert {a["name"]: a["harness"] for a in listing}["cli-claude"] == "claude"
    bad = runner.invoke(app, ["community", "--root", str(root), "add-agent", "x", "--harness", "claude",
                              "--harness-options", '{"args": []}'])
    assert isinstance(bad.exception, DawError) and bad.exception.reason == "invalid_harness_options"


def test_scripted_adapter_sniffs_stream_formats(tmp_path):
    for first, fmt in (({"type": "system", "session_id": "s"}, "hermes"), ({"type": "system", "subtype": "init"}, "claude"),
                       ({"type": "thread.started"}, "codex"), ({"type": "session", "id": "x"}, "jsonl")):
        path = tmp_path / f"{fmt}.jsonl"
        path.write_text(json.dumps(first) + "\n")
        assert scripted.sniff(path) == fmt
    assert scripted.install(tmp_path / "bin/h").endswith("bin/h") and (tmp_path / "bin/h").stat().st_mode & 0o100


def test_bio_mcp_serve_speaks_json_rpc_over_stdio(demo):
    from typer.testing import CliRunner

    from daw.bio_cli import app
    root, _ = demo
    with Community(root) as board:
        trial = board.trial(board.agent("bob"))
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": 2, "method": "ping"}]
    result = CliRunner().invoke(app, ["mcp", "serve", "--checkout", str(trial)],
                                input="\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    assert result.exit_code == 0, result.output
    responses = [json.loads(line) for line in result.output.splitlines()]
    assert [r.get("id") for r in responses] == [1, 2, None]
    assert responses[0]["result"]["protocolVersion"] == "2025-06-18" and responses[2]["error"]["code"] == -32700


def test_cli_cohort_run_dispatches_and_records_cohorts(demo, tmp_path):
    from typer.testing import CliRunner

    from daw.bio_cli import app
    root, _ = demo
    files = []
    for n in range(2):
        path = tmp_path / f"a{n}.md"
        path.write_text(f"# Assignment {n}\nInvestigate fixture {n}.\n")
        files += ["--assignment", str(path)]
    with scripted_runtime(root) as (executable, _):
        with Community(root) as board:
            add_agent(board, "claude-two", harness="claude")
        result = CliRunner().invoke(app, ["commons", "--root", str(root), "cohort-run", "cli", *files, "--agent", "bob",
                                          "--agent", "claude-two", "--minutes", "5", "--dispatch",
                                          "--harness-executable", f"hermes={executable}",
                                          "--harness-executable", f"claude={executable}"])
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert set(value["delivered"].values()) == {"completed"} and len(value["cohorts"]) == 2
