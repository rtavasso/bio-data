"""Runtime area (M3.3–M3.6): harness adapters, task types, budgets and clocks, delivery rules, sandbox."""
import asyncio
import hashlib
import json
import os
import sys
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
from daw.util import DawError, read_json

def events(board, kind):
    return [json.loads(r["body"]) for r in board.rows("SELECT body FROM event WHERE kind=? ORDER BY seq", (kind,))]


FAKE_ENGINE = r'''
import json, os, sys
from pathlib import Path
argv = sys.argv[1:]
with open(LOG, "a") as log:
    log.write(json.dumps(argv) + "\n")
if argv[:1] != ["run"]:
    sys.exit(0)
VALUED = {"--name", "--label", "--network", "--cap-drop", "--security-opt", "--pids-limit", "--user", "--workdir",
          "--tmpfs", "--memory", "--cpus", "--mount", "--env"}
env, workdir, i = {"PATH": os.environ.get("PATH", "")}, None, 1
while argv[i].startswith("-"):
    flag = argv[i]
    if flag in VALUED:
        value = argv[i + 1]
        if flag == "--env":
            key, sep, given = value.partition("=")
            if sep:
                env[key] = given
            elif key in os.environ:
                env[key] = os.environ[key]
        elif flag == "--workdir":
            workdir = value
        i += 2
    else:
        i += 1
image, command = argv[i], argv[i + 1:]
if any(part.endswith("hermes_session_bridge.py") for part in command):
    # Stand-in for Hermes's SessionDB inside the image (the demo's bridge substitute on the scripted state.db).
    from daw.commons.demo import _fake_native_session
    at = command.index("--session")
    print(json.dumps(_fake_native_session(None, Path(env["HERMES_HOME"]), command[at + 1], env["HERMES_CWD"],
                                          fork="--fork" in command)))
    sys.exit(0)
os.chdir(workdir)
os.execvpe(command[0], command, env)
'''


def fake_engine(folder, monkeypatch):
    """A `docker` stand-in on PATH that logs its argv and runs the containerized command on the host
    (no isolation: it checks the dispatch path and receipts, never the container boundary)."""
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / "engine.jsonl"
    engine = folder / "docker"
    engine.write_text(f"#!{sys.executable}\nLOG = {str(log)!r}\n" + FAKE_ENGINE)
    engine.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}:{os.environ.get('PATH', '')}")
    return lambda: [json.loads(line) for line in log.read_text().splitlines()] if log.is_file() else []


def operator_notices(board):
    return [board.show(r["post"])["content"]["title"] for r in board.inbox("operator", all_states=True)
            if r["task_type"] == tasks.NOTICE]


def answer_for(answers, request, board, text):
    (answers / f"{board.one('SELECT post FROM request WHERE id=?', (request['id'],))['post']}.md").write_text(text)


def comment(board, author, post, body):
    """A person's anchored comment that asks the post's author (daw.commons.participation)."""
    from daw.commons.participation import comment as post_comment
    shown = board.show(post)
    quote = shown["content"]["body"].split(" (")[0][:20]
    return post_comment(board, author, "post", post, body, ask_author=True,
                        anchor={"kind": "paragraph", "blob": shown["body_blob"], "offset": 0, "length": len(quote),
                                "quote": quote})["request"]


# ---- M3.3 adapters ------------------------------------------------------------------------------

def test_registry_and_legacy_hermes_prompt_is_byte_identical():
    assert [harness.get(n).name for n in harness.NAMES] == list(harness.NAMES)
    assert harness.for_agent({"config": {}}).name == "hermes"
    with pytest.raises(DawError, match="unknown_harness"):
        harness.get("copilot")
    post = {"id": "post_123", "parent": None, "content": {"body": "Body"}}
    trial = Path("/x/agents/agent_abc/trial")
    # Frozen digests of the assignment prompt (question and answer notification). Spec v2 V1 changed exactly one
    # sentence deliberately: the final-answer structure is now "claims first (a fenced ```claims block), prose
    # second". The digests were re-frozen for that change only; swapping the old final-answer sentence back in
    # must reproduce the pre-V1 digests, so any other drift in the legacy Hermes prompt still fails here.
    new = hashlib.sha256(assignment_prompt("agent_abc", trial, post).encode()).hexdigest()
    assert new == "68a4bbdd2389b5b93f8f3aa4afaedcd1f335108937786b7c58bfa71f85812f60"
    assert hashlib.sha256(assignment_prompt("agent_abc", trial, post, notification=True).encode()).hexdigest() == \
        "c4662da6144c2820fd229e5bd8661076a907554b468bb33c3bc144b3a121416a"
    from daw import community_runtime
    v1_sentence = community_runtime.ANALYSIS[community_runtime.ANALYSIS.index("Structure it claims first"):]
    pre_v1 = ("Structure it as: the finding, the evidence pointers (posts, artifacts, notebook), its limits, and the "
              "next computable step. Receipt and lint details stay in the LABBOOK.\n")
    old = assignment_prompt("agent_abc", trial, post).replace(v1_sentence, pre_v1)
    assert hashlib.sha256(old.encode()).hexdigest() == "202c1b97fdde02cac89b77d9347c4eea3ba7aedf79db4ad68977a40af7fa7e12"
    old = assignment_prompt("agent_abc", trial, post, notification=True).replace(v1_sentence, pre_v1)
    assert hashlib.sha256(old.encode()).hexdigest() == "371f700ecf9f10dfef009fe03beaa69e4f52c115fcfcfe39bd6f435b08012dce"


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
        human_comment = comment(board, rhea["id"], ctx["posts"]["finding"], "Is this paired?")
        assert human_comment["target"] == alice
        fresh_post = board.publish(fresh["id"], "Prepared note", "A note from an agent that never ran.")
        unstarted_comment = comment(board, rhea["id"], fresh_post["id"], "And here?")
        from daw.commons.participation import promote
        promoted = promote(board, rhea["id"], "post", ctx["posts"]["gap"], "scouting", fresh["id"], {"minutes": 5})
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
        assert "COMMENT by human participant rhea on post " in prompt and "Quoted passage" in prompt
        dispatch(board, promoted["id"], executable)  # never ran before: a person authorized this task
        prompt = (_run_folder(board, promoted) / "prompt.txt").read_text()
        assert "This is a SCOUTING task" in prompt and f"Subject: post {ctx['posts']['gap']}." in prompt
        assert events(board, "task_outcome")[-1]["criteria"]["analysis_out_of_scope"]


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
        # The agent's transport reads the caps from the platform-owned task budget file (spec v2 C7).
        hook.write_text("import json\nfrom daw.catalog import Workspace\nws = Workspace('workspace')\n"
                        "open('budgets-during-task.json', 'w').write(json.dumps({'bundle': ws.budgets.bundle_bytes, "
                        "'asset': ws.budgets.asset_bytes}))\nws.close()\n")
        config_before = (board.trial(board.agent("bob")) / "workspace/config.toml").read_bytes()
        dispatch(board, request["id"], executable)
        folder = _run_folder(board, request)
        prompt = (folder / "prompt.txt").read_text()
        assert prompt.startswith("You are a researcher") and "TASK TYPE: research" in prompt
        assert "30 minutes" in prompt and "Deadline: 2099-01-01T00:00:00+00:00" in prompt
        assert read_json(folder / "execution.json")["timeout_seconds"] == 1800
        trial = board.trial(board.agent("bob"))
        assert read_json(trial / "budgets-during-task.json") == {"bundle": 4096, "asset": 4096}
        # The agent-writable config is never touched, and the task file is gone after the turn.
        assert (trial / "workspace/config.toml").read_bytes() == config_before
        assert not (trial / budgets.TASK_BUDGET).exists() and (trial / ".colloquy").is_dir()
        receipt = read_json(folder / "budget.json")
        assert receipt["download_bytes"]["applied"]["bundle_bytes"] == 4096
        assert receipt["download_bytes"]["observed"] == "unchanged" and not receipt["download_bytes"]["policy_violation"]
        assert not receipt["download_bytes"]["workspace_config_touched"]
        assert not events(board, "budget_policy_violation")
        # Harness telemetry (1200 input + 450 output) is checked against the limit after the turn, not enforced;
        # the exceedance is a board event and an operator notice.
        assert receipt["tokens"]["used"] == 1650 and receipt["tokens"]["exceeded"] is True
        [exceeded] = events(board, "token_budget_exceeded")
        assert exceeded == {"request": request["id"], "run": folder.name, "agent": ctx["agents"]["bob"], "limit": 1000,
                            "used": 1650, "counted": ["input_tokens", "output_tokens"]}
        assert "Token budget exceeded: bob" in operator_notices(board)
        # The demo board also holds the participation demo's answered ask (a typed `question` request since v2 C4).
        [outcome] = [e for e in events(board, "task_outcome") if e["request"] == request["id"]]
        assert outcome["task_type"] == "research" and outcome["request"] == request["id"]
        assert outcome["criteria"]["pointers"]["unresolved"] == [f"post_{'0' * 32}"]
        assert ctx["artifacts"]["normalized"] not in outcome["criteria"]["pointers"]["unresolved"]
        assert outcome["criteria"]["budget"]["tokens"] == receipt["tokens"]
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


@pytest.mark.parametrize("executed", [True, False])
def test_replication_outcome_is_gated_on_an_execution_receipt(demo, executed):
    """C6: the runtime counts a same-derivation registration only under a run_analysis receipt of the derivation's
    code; the original's fork is refused; local mode records the unsandboxed-execution warning."""
    from daw.commons import studio_demo
    root, ctx = demo
    original = ctx["artifacts"]["contrast"]
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        with pytest.raises(DawError, match="replication_target_produced_original"):
            assign(board, "operator", board.agent("alice-fork")["id"], "Replicate", "Replicate the contrast.",
                   task_type="replication", evidence={"subject_kind": "artifact", "subject_id": original})
        request = assign(board, "operator", ctx["agents"]["bob"], "Replicate", "Replicate the contrast.",
                         task_type="replication", evidence={"subject_kind": "artifact", "subject_id": original})
        hook = (studio_demo.replication_hook(ctx["posts"]["finding"], original) if executed else
                "import os\nfrom daw.artifacts import artifact_info, register_artifact\nfrom daw.catalog import Workspace\n"
                "from daw.substrate_models import ArtifactRegistration, Derivation\nfrom daw.work import create_question\n"
                "ws = Workspace(os.environ['BIO_WORKSPACE'])\nwith ws.writer():\n"
                f"    info = artifact_info(ws, {original!r})\n"
                "    q = create_question(ws, 'Replicate')['question']\n"
                "    open('copied.tsv', 'wb').write(ws.blob_path(info['output_blob']).read_bytes())\n"
                "    register_artifact(ws, 'copied.tsv', ArtifactRegistration(title='Copy', summary='copied',\n"
                "        output_role=info['manifest']['output_role'], derivation=Derivation(**info['manifest']['derivation'])),\n"
                "        question=q)\nws.close()\n")
        answer_for(answers, request, board, "Replicated.")
        (answers / f"{request['post']}.hook.py").write_text(hook)
        notices = len(events(board, "notice_queued"))
        done = dispatch(board, request["id"], executable)
        prompt = (root / "runs" / done["active_run"] / "prompt.txt").read_text()
        assert "replicate.py" in prompt and "permission to execute downloaded code" not in prompt
        assert read_json(root / "runs" / done["active_run"] / "sandbox.json")["warning"].startswith("replication_unsandboxed")
        outcome = events(board, "task_outcome")[-1]
        [result] = outcome["criteria"]["replication"]
        if executed:
            assert result["outcome"] == "byte_identical" and result["identical"] == [original]
            assert result["receipts"][original]["exit_code"] == 0 and f"artifact:{original}" in outcome["deliverables_found"]
        else:
            assert result["outcome"] == "no_execution_receipt" and not result["identical"]
            assert not result["correction_required"] and f"artifact:{original}" not in outcome["deliverables_found"]
        assert len(events(board, "notice_queued")) == notices


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
    # The board root is never mounted, so other checkouts, runs/, service/ and secrets/ are absent.
    assert not any(f"src={root}," in m or f"src={root / 'runs'}" in m or f"src={root / 'agents'}," in m for m in mounts)
    assert all(m.split("src=")[1].startswith((str(trial), str(auth))) for m in mounts if "src=" in m)
    assert f"type=bind,src={auth},dst={auth},readonly" in mounts
    assert argv[argv.index("--network") + 1] == "egress-net" and "--read-only" in argv and "ALL" in argv
    assert "/tmp:rw,size=1048576,mode=1777" in argv and client["HTTPS_PROXY"] == "http://egress:3128"
    assert "api.anthropic.com" in sandbox.hosts(config, claude.ADAPTER.hosts({})) and "zenodo.org" in sandbox.hosts(None)
    (root / "sandbox.toml").write_text('engine = "lxc"\n')
    with pytest.raises(DawError, match="invalid_sandbox_config"):
        sandbox.load(root)


def test_multi_tenant_dispatch_requires_a_sandbox_or_a_recorded_override(demo, tmp_path, monkeypatch):
    root, ctx = demo
    engine_calls = fake_engine(tmp_path / "engine", monkeypatch)
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
        # A configured sandbox wraps the harness argv in the container engine (a logging stand-in here: the
        # engine runs the command on the host, so this checks the dispatch path, not container isolation).
        (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\n')
        wrapped = board.ask("bob", ctx["agents"]["alice"], "Contained")
        session = board.agent("bob")["native_session"]
        assert board.agent("bob")["config"]["harness"] == "hermes" and session
        monkeypatch.setattr("daw.community_runtime.native_session", lambda *a, **k: pytest.fail("host Hermes used"))
        assert dispatch(board, wrapped["id"], executable)["state"] == "completed"
        folder = _run_folder(board, wrapped)
        receipt = read_json(folder / "sandbox.json")
        assert receipt["sandboxed"] and receipt["network"] == "none" and receipt["harness_argv"][0] == executable
        assert receipt["board_mounted"] is False and receipt["board_service"]["url"].startswith("unix://")
        assert read_json(folder / "execution.json")["argv"][:2] == ["docker", "run"]
        # Sandboxed Hermes resume: the session bridge ran inside the agent image, without network.
        bridge, run = [c for c in engine_calls() if c[0] == "run"]
        assert any(part.endswith("src/daw/hermes_session_bridge.py") for part in bridge)
        assert bridge[bridge.index("--network") + 1] == "none" and "agent:1" in bridge and "HERMES_HOME" in bridge
        assert read_json(folder / "native-session.json")["bridge"] == "agent image"
        assert board.agent("bob")["native_session"] == session
        # The sealed harness configuration is mounted read-only over the home.
        trial = board.trial(board.agent("bob"))
        sealed = sandbox.harness_config_dir(trial).resolve() / "config.yaml"
        assert f"type=bind,src={sealed},dst={trial.resolve() / '.hermes/config.yaml'},readonly" in run
        assert receipt["harness_config_read_only"] == [str(trial.resolve() / ".hermes/config.yaml")]
        # An image without a Python Hermes entry point is refused with a named error, before any turn runs.
        engine = tmp_path / "engine" / "docker"
        engine.write_text(engine.read_text().replace("from daw.commons.demo", "sys.stderr.write('hermes_python_"
                                                                                "unavailable'); sys.exit(3)\n    from x"))
        refused = board.ask("bob", ctx["agents"]["alice"], "Again")
        with pytest.raises(DawError, match="hermes_python_unavailable"):
            dispatch(board, refused["id"], executable)
        assert not (_run_folder(board, refused) / "events.jsonl").exists()


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


# ---- spec v2 C7: token-scoped egress, platform-owned budgets, sealed harness homes ----------------

def _through_proxy(proxy_port, target, credential=None):
    """CONNECT through the proxy (optionally with a Basic credential); returns (status line, upstream reply)."""
    import base64

    async def go():
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        auth = ""
        if credential:
            auth = "Proxy-Authorization: Basic " + base64.b64encode(credential.encode()).decode() + "\r\n"
        writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n{auth}\r\n".encode())
        await writer.drain()
        status = (await reader.readuntil(b"\r\n\r\n")).split(b"\r\n")[0]
        body = b""
        if b" 200 " in status:
            writer.write(b"hello")
            await writer.drain()
            body = await reader.read(100)
        writer.close()
        return status, body
    return go


def test_agent_added_after_proxy_start_reaches_its_provider_host(demo, tmp_path):
    """C7 acceptance: the allowlist is computed per dispatch and read per connection, not frozen at start."""
    from urllib.parse import urlsplit
    root, ctx = demo
    (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\nnetwork = "colloquy-egress"\n'
                                       'proxy = "http://egress:3128"\n')
    log = tmp_path / "egress.jsonl"
    outcome = {}

    async def scenario():
        async def provider(reader, writer):  # a local fake upstream standing in for api.anthropic.com
            writer.write(b"provider:" + await reader.read(5))
            await writer.drain()
            writer.close()
        upstream = await asyncio.start_server(provider, "127.0.0.1", 0)
        port = upstream.sockets[0].getsockname()[1]
        base = egress.Policy((), ports=(port,), allow_private=True, resolver=lambda host, p: ["127.0.0.1"])
        proxy = await egress.start(egress.PolicyStore(egress.policy_dir(root), base), "127.0.0.1", 0, log)
        proxy_port = proxy.sockets[0].getsockname()[1]
        loop = asyncio.get_running_loop()

        def dispatch_side():
            # The proxy is already running; now a Claude agent joins and one delivery is wrapped.
            with Community(root) as board:
                agent = add_agent(board, "late-claude", harness="claude")
                trial = board.trial(agent)
                env = {"BIO_AGENT": agent["id"], "BIO_COMMUNITY": str(root), "PATH": "/usr/bin"}
                decision = sandbox.policy(root)
                _, client, receipt = sandbox.apply(decision, ["claude", "-p"], env, trial=trial, board_root=root,
                                                   adapter=claude.ADAPTER, agent_config=agent["config"], run="run_late",
                                                   timeout=600)
                hermes_env = {**env, "BIO_AGENT": ctx["agents"]["alice"]}
                _, other, other_receipt = sandbox.apply(
                    decision, ["hermes"], hermes_env, trial=board.trial(board.agent("alice")), board_root=root,
                    adapter=harness.get("hermes"), agent_config=board.agent("alice")["config"], run="run_alice")
            return client, receipt, other, other_receipt
        client, receipt, other, other_receipt = await loop.run_in_executor(None, dispatch_side)
        url = urlsplit(client["HTTPS_PROXY"])
        credential = f"{url.username}:{url.password}"
        alice_url = urlsplit(other["HTTPS_PROXY"])
        outcome.update(
            client=client, receipt=receipt, other_receipt=other_receipt,
            provider=await _through_proxy(proxy_port, f"api.anthropic.com:{port}", credential)(),
            source=await _through_proxy(proxy_port, f"www.ebi.ac.uk:{port}", credential)(),
            elsewhere=await _through_proxy(proxy_port, f"evil.example:{port}", credential)(),
            anonymous=await _through_proxy(proxy_port, f"api.anthropic.com:{port}")(),
            forged=await _through_proxy(proxy_port, f"api.anthropic.com:{port}", "run_late:not-the-token")(),
            hermes=await _through_proxy(proxy_port, f"api.anthropic.com:{port}",
                                        f"{alice_url.username}:{alice_url.password}")())
        sandbox.release(root, receipt)
        outcome["revoked"] = await _through_proxy(proxy_port, f"api.anthropic.com:{port}", credential)()
        proxy.close()
        upstream.close()
    asyncio.run(scenario())
    assert b" 200 " in outcome["provider"][0] and outcome["provider"][1] == b"provider:hello"
    assert b" 200 " in outcome["source"][0]  # source adapter hosts are part of every dispatch's policy
    assert b" 403 " in outcome["elsewhere"][0]
    assert b" 407 " in outcome["anonymous"][0] and b" 407 " in outcome["forged"][0] and b" 407 " in outcome["revoked"][0]
    assert b" 403 " in outcome["hermes"][0]  # another agent's credential does not open Claude's provider host
    receipt = outcome["receipt"]
    assert receipt["egress"]["scope"] == "token-scoped policy" and receipt["egress"]["revoked"]
    assert "api.anthropic.com" in receipt["egress_allowlist"] and "zenodo.org" in receipt["egress_allowlist"]
    token = urlsplit(outcome["client"]["HTTPS_PROXY"]).password
    assert token not in json.dumps(receipt) and token not in log.read_text()
    assert not (egress.policy_dir(root) / (receipt["egress"]["policy"] + ".json")).exists()
    decisions = [json.loads(line) for line in log.read_text().splitlines()]
    assert {d["reason"] for d in decisions} >= {"allowed", "host_not_allowlisted", "proxy_credential_required",
                                                "proxy_credential_invalid"}
    assert any(d.get("run") == "run_late" and d["allowed"] for d in decisions)
    # Plain-HTTP requests never carry the dispatch credential upstream.
    head = egress.parse_head(b"GET http://www.ebi.ac.uk/x HTTP/1.1\r\nHost: www.ebi.ac.uk\r\n"
                             b"Proxy-Authorization: Basic abc\r\n\r\n")[3]
    assert b"Proxy-Authorization" not in head and b"Host: www.ebi.ac.uk" in head


def test_replication_egress_is_enforced_by_its_token_scoped_proxy_policy(demo):
    """C6 x C7: a replication's model-hosts-only allowlist is the policy its proxy credential opens."""
    import base64
    from urllib.parse import urlsplit
    root, ctx = demo
    (root / "sandbox.toml").write_text('engine = "docker"\nimage = "agent:1"\nnetwork = "egress"\n'
                                       'proxy = "http://egress:3128"\nallow_hosts = ["example.org"]\n')
    with Community(root) as board:
        agent = add_agent(board, "rep-claude", harness="claude")
        trial = board.trial(agent)
    env = {"BIO_AGENT": agent["id"], "BIO_COMMUNITY": str(root), "PATH": "/usr/bin"}
    store = egress.PolicyStore(egress.policy_dir(root), egress.Policy((), resolver=lambda h, p: ["93.184.216.34"]))
    scoped = {}
    for task_type in ("replication", "research"):
        _, client, receipt = sandbox.apply(sandbox.policy(root, None, task_type), ["claude"], env, trial=trial,
                                           board_root=root, adapter=claude.ADAPTER, agent_config=agent["config"],
                                           run=f"run_{task_type}")
        url = urlsplit(client["HTTPS_PROXY"])
        header = "Basic " + base64.b64encode(f"{url.username}:{url.password}".encode()).decode()
        policy, reason, record = store.resolve(header)
        assert reason == "ok" and record["hosts"] == receipt["egress_allowlist"]
        scoped[task_type] = policy
    assert scoped["replication"].check("api.anthropic.com", 443)[0]
    assert scoped["replication"].check("zenodo.org", 443)[1] == "host_not_allowlisted"
    assert scoped["replication"].check("example.org", 443)[1] == "host_not_allowlisted"
    assert scoped["research"].check("zenodo.org", 443)[0] and scoped["research"].check("example.org", 443)[0]


def test_budget_file_edit_raises_a_policy_violation_event(demo):
    """C7 acceptance: an agent that changes its platform-owned budget file triggers budget_policy_violation
    and an operator notice; the changed bytes are kept for audit."""
    root, ctx = demo
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        request = assign(board, "operator", ctx["agents"]["bob"], "Bounded", "Fetch at most 4 KiB.",
                         budget={"download_bytes": 4096})
        hook = answers / f"{request['post']}.hook.py"
        hook.write_text("import os, json\np = '.colloquy/task-budget.json'\nos.chmod(p, 0o600)\n"
                        "d = json.load(open(p))\nd['caps'] = {'bundle_bytes': 10**12, 'asset_bytes': 10**12}\n"
                        "open(p, 'w').write(json.dumps(d))\n")
        dispatch(board, request["id"], executable)
        folder = _run_folder(board, request)
        receipt = read_json(folder / "budget.json")["download_bytes"]
        assert receipt["policy_violation"] and receipt["observed"] == "changed"
        assert receipt["observed_sha256"] != receipt["sha256"]
        assert read_json(folder / "task-budget-observed.json")["caps"]["bundle_bytes"] == 10**12
        [violation] = events(board, "budget_policy_violation")
        assert violation == {"request": request["id"], "run": folder.name, "agent": ctx["agents"]["bob"],
                             "file": ".colloquy/task-budget.json", "expected_sha256": receipt["sha256"],
                             "observed": "changed", "observed_sha256": receipt["observed_sha256"]}
        assert "Budget policy violation: bob" in operator_notices(board)
        trial = board.trial(board.agent("bob"))
        assert not (trial / budgets.TASK_BUDGET).exists()
        # Removing the file is a violation too.
        removed = assign(board, "operator", ctx["agents"]["bob"], "Bounded again", "Same.", budget={"download_bytes": 1})
        (answers / f"{removed['post']}.hook.py").write_text("import os\nos.remove('.colloquy/task-budget.json')\n")
        dispatch(board, removed["id"], executable)
        assert events(board, "budget_policy_violation")[-1]["observed"] == "removed"


def test_transport_reads_task_caps_and_fails_closed(tmp_path):
    from daw.catalog import Workspace
    trial = tmp_path / "trial"
    Workspace.create(trial / "workspace").close()
    receipt = {}
    with budgets.download_budget(trial, {"download_bytes": 2048}, receipt, run="run_x"):
        ws = Workspace(trial / "workspace")
        assert (ws.budgets.bundle_bytes, ws.budgets.asset_bytes) == (2048, 2048)
        ws.close()
        path = trial / budgets.TASK_BUDGET
        assert path.stat().st_mode & 0o222 == 0  # read-only even outside the sandbox
    assert receipt["download_bytes"]["observed"] == "unchanged"
    assert Workspace(trial / "workspace").budgets.bundle_bytes == 0  # unlimited again after the task
    (trial / budgets.TASK_BUDGET).write_text("not json")
    with pytest.raises(DawError, match="task_budget_invalid"):
        Workspace(trial / "workspace")
    budgets.clear_task_budget(trial)
    assert Workspace(trial / "workspace").budgets.bundle_bytes == 0


def test_a_second_workspace_inside_the_checkout_still_hits_the_task_cap(demo, monkeypatch):
    """v3 B5: the task budget is resolved from the checkout root (and the running agent's home), so a workspace
    the agent initialises anywhere inside its checkout is capped like `<checkout>/workspace`; the board service
    reads and writes only the checkout workspace."""
    from daw.catalog import Workspace
    from daw.commons import boardservice
    monkeypatch.delenv("BIO_WORKSPACE", raising=False)
    root, ctx = demo
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        request = assign(board, "operator", ctx["agents"]["bob"], "Bounded", "Stay within the cap.",
                         budget={"download_bytes": 4096})
        answer_for(answers, request, board, "Done.")
        # As `bio init sub/ws` would, in the checkout and beside it (found through BIO_AGENT's home).
        (answers / f"{request['post']}.hook.py").write_text(
            "import json, os\nfrom pathlib import Path\nfrom daw.catalog import Workspace\ncaps = {}\n"
            "for name in ('sub/ws', 'deep/er/ws', '../outside-ws'):\n"
            "    ws = Workspace.create(name)\n"
            "    caps[name] = [ws.budgets.bundle_bytes, ws.budgets.asset_bytes]\n    ws.close()\n"
            "Path('caps-during-task.json').write_text(json.dumps(caps))\n")
        dispatch(board, request["id"], executable)
        trial = board.trial(board.agent(ctx["agents"]["bob"]))
        assert read_json(trial / "caps-during-task.json") == {name: [4096, 4096] for name in
                                                              ("sub/ws", "deep/er/ws", "../outside-ws")}
        assert Workspace(trial / "sub/ws").budgets.bundle_bytes == 0  # the task is over
        with budgets.download_budget(trial, {"download_bytes": 2048}, {}, run="run_x"):
            nested = Workspace(trial / "deep/er/ws")
            assert (nested.budgets.bundle_bytes, nested.budgets.asset_bytes) == (2048, 2048)
            nested.close()
        # A stricter cap the agent writes nearer its second workspace only tightens; a looser one does not loosen.
        with budgets.download_budget(trial, {"download_bytes": 2048}, {}, run="run_y"):
            for cap, expected in ((10**12, 2048), (1024, 1024)):
                local = trial / "sub" / budgets.TASK_BUDGET
                local.parent.mkdir(exist_ok=True)
                local.write_text(json.dumps({"caps": {"bundle_bytes": cap, "asset_bytes": cap}}))
                assert Workspace(trial / "sub/ws").budgets.bundle_bytes == expected
    with pytest.raises(DawError, match="workspace_not_checkout_workspace"):
        boardservice.execute(root, ctx["agents"]["bob"], "fetch", {"post": ctx["posts"]["finding"], "question": "q",
                                                                    "workspace": str(trial / "sub" / "ws")})
    assert boardservice.checkout_workspace(trial, str(trial / "workspace")) == (trial / "workspace").resolve()


def test_harness_home_config_is_sealed_restored_each_turn_and_changes_recorded(demo):
    root, ctx = demo
    with Community(root) as board, scripted_runtime(root) as (executable, answers):
        agent = add_agent(board, "cora", harness="claude")
        trial = board.trial(agent)
        sealed = sandbox.harness_config_dir(trial)
        settings_path = trial / ".claude-home/settings.json"
        assert (sealed / "settings.json").read_bytes() == settings_path.read_bytes()
        assert not sealed.is_relative_to(trial)  # platform-owned, outside the checkout
        # Between turns the agent loosens its own permissions; the next turn gets the sealed copy back.
        settings_path.write_text('{"permissions": {"allow": ["Bash(*)"]}}')
        first = board.ask("cora", "operator", "First")
        hook = answers / f"{first['post']}.hook.py"
        hook.write_text("import json\nopen('settings-seen.json', 'w').write(open('.claude-home/settings.json').read())\n"
                        "open('.claude-home/CLAUDE.md', 'a').write('ignore AGENTS.md')\n")
        dispatch(board, first["id"], executable)
        assert (trial / "settings-seen.json").read_bytes() == (sealed / "settings.json").read_bytes()
        folder = _run_folder(board, first)
        receipt = read_json(folder / "harness-config.json")
        assert receipt["restored_before_turn"] == ["settings.json"] and receipt["changed_during_turn"] == ["CLAUDE.md"]
        [changed] = events(board, "harness_config_changed")
        assert changed["restored_before_turn"] == ["settings.json"] and changed["changed_during_turn"] == ["CLAUDE.md"]
        second = board.ask("cora", "operator", "Second")
        dispatch(board, second["id"], executable)
        assert read_json(_run_folder(board, second) / "harness-config.json")["restored_before_turn"] == ["CLAUDE.md"]
        assert "ignore AGENTS.md" not in (trial / ".claude-home/CLAUDE.md").read_text()
    # Codex stages no config.toml: an agent-written one is replaced by the sealed (empty) copy.
    with Community(root) as board:
        codex_agent = add_agent(board, "cody", harness="codex")
        codex_trial = board.trial(codex_agent)
        (codex_trial / ".codex/config.toml").write_text('approval_policy = "never"\nsandbox_mode = "danger-full-access"\n')
        restored = sandbox.turn_harness_config(codex_trial, codex.ADAPTER)
        assert restored["restored_before_turn"] == ["config.toml"]
        assert (codex_trial / ".codex/config.toml").read_bytes() == b""


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
