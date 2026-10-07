"""Deterministic scripted harness for offline tests and the synthetic demo (no model, credential or network).

`SCRIPT` is a stand-in executable that speaks the stream and session protocol
of a stock harness, chosen from its argv: the Hermes CLI (`chat ...`), Claude
Code (`-p --output-format stream-json`), Codex (`exec --json`), or, for the
`scripted` adapter, `--stream-format hermes|claude|codex|jsonl`. It keeps native
session state where the real harness would, so resume and fork go through the
real adapters. Answers come from `$COLLOQUY_DEMO_ANSWERS/<post>.md`; an
optional `<post>.hook.py` written by a test runs inside the checkout first
(fixture code, never downloaded content); a `CALLS` list it defines
(`{command, exit_code, output}`) is emitted as terminal calls after the fixed ones,
so the commands a hook ran are in the captured stream as an agent's would be. A `scripted-sleep` file in the
checkout makes the harness pause without output for that many seconds (stall
tests); `fail-next` makes one turn fail; `scripted-compaction` (text `summary` or `fallback`)
writes a compaction summary mid-turn where the harness keeps it: a message in the session database (Hermes)
or an `isCompactSummary` transcript entry (Claude Code, whose stream also carries a `compact_boundary`).
"""
import json
import sys
from pathlib import Path

from daw.harness import claude, codex, hermes, mcp
from daw.harness.base import Adapter
from daw.util import DawError

SCRIPT = r'''import json, os, re, runpy, shutil, sqlite3, sys, time, uuid
from pathlib import Path
argv = sys.argv[1:]
prompt = sys.stdin.read()
if "--stream-format" in argv:
    fmt = argv[argv.index("--stream-format") + 1]
    home, trial = Path(argv[argv.index("--home") + 1]), Path.cwd()
    store = "db"
elif argv[:1] == ["chat"]:
    fmt, home, trial = "hermes", Path(os.environ["HERMES_HOME"]), Path(os.environ["HERMES_CWD"])
elif "-p" in argv:
    fmt, home, trial = "claude", Path(os.environ["CLAUDE_CONFIG_DIR"]), Path.cwd()
elif "exec" in argv:
    fmt, home, trial = "codex", Path(os.environ["CODEX_HOME"]), Path.cwd()
else:
    sys.exit("unrecognized harness invocation")
store = locals().get("store") or fmt
resume = None
for flag in ("--resume", "resume"):
    if flag in argv:
        resume = argv[argv.index(flag) + 1]
sid = resume or ("native_" + uuid.uuid4().hex if fmt in ("hermes", "jsonl") else str(uuid.uuid4()))
if store == "claude":
    # Claude Code files a conversation per working directory; --fork-session branches it under a new id.
    folder = home / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(trial))
    folder.mkdir(parents=True, exist_ok=True)
    if resume and not (folder / (resume + ".jsonl")).is_file():
        sys.exit("unknown session")
    if resume and "--fork-session" in argv:
        sid = str(uuid.uuid4())
        shutil.copyfile(folder / (resume + ".jsonl"), folder / (sid + ".jsonl"))
    with (folder / (sid + ".jsonl")).open("a") as log:
        log.write(json.dumps({"type": "user", "message": prompt[:200]}) + "\n")
    turns = len((folder / (sid + ".jsonl")).read_text().splitlines())
else:
    db = sqlite3.connect(home / "state.db")
    db.execute("CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, cwd TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS messages(session TEXT, content TEXT, timestamp REAL)")
    if not resume:
        db.execute("INSERT INTO sessions VALUES(?,?)", (sid, str(trial)))
    elif not db.execute("SELECT id FROM sessions WHERE id=?", (resume,)).fetchone():
        sys.exit("unknown session")
    db.execute("INSERT INTO messages VALUES(?,?,?)", (sid, prompt, time.time()))
    db.commit()
    turns = db.execute("SELECT count(*) FROM messages WHERE session=?", (sid,)).fetchone()[0]
    db.close()
if store == "codex":
    folder = home / "sessions" / "2026" / "01" / "01"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ("rollout-scripted-" + sid + ".jsonl")).open("a") as log:
        log.write(json.dumps({"type": "session_meta", "id": sid}) + "\n")
found = re.search(r"(?:Question|Request) post: (post_[0-9a-f]+)", prompt)
post = found.group(1) if found else ""
answers = Path(os.environ.get("COLLOQUY_DEMO_ANSWERS", "/nonexistent"))
hook = answers / (post + ".hook.py")
hooked = runpy.run_path(str(hook), run_name="__main__") if post and hook.is_file() else {}
answer = (answers / (post + ".md")).read_text() if post and (answers / (post + ".md")).is_file() else "No change to my conclusions."
answer = answer.replace("{turns}", str(turns))
pause = trial / "scripted-sleep"
failed = (trial / "fail-next").exists()
if failed:
    (trial / "fail-next").unlink()
clock = int(time.time() * 1000)
def emit(value, step=1500):
    global clock
    clock += step
    if fmt == "hermes":
        value["timestamp"] = clock
    print(json.dumps(value), flush=True)
calls = [("terminal", {"command": "./bin/bio community search --text PMP22"}, {"exit_code": 0, "output": "3 hits"}),
         ("terminal", {"command": "./bin/bio community inbox --sent"}, {"exit_code": 0, "output": "[]"}),
         ("read_file", {"path": "workspace/questions/LABBOOK.md"}, None),
         ("terminal", {"command": "./bin/python .agents/skills/bio-research/scripts/run_analysis.py scripts/contrast.py"},
          {"exit_code": 0, "output": "receipt written"}),
         ("terminal", {"command": "./bin/python .agents/skills/bio-research/scripts/run_analysis.py scripts/check.py"},
          {"exit_code": 1, "output": "assertion failed: column missing"}),
         ("terminal", {"command": "./bin/bio register outputs/contrast.tsv --output-role contrast-table"},
          {"exit_code": 0, "output": "registered"})]
# Terminal calls the hook made (its CALLS list), emitted as the agent's own captured tool calls.
calls += [("terminal", {"command": c["command"]}, {"exit_code": c.get("exit_code", 0), "output": c.get("output", "")})
          for c in hooked.get("CALLS", [])]
usage ={"input_tokens": 1200, "cached_input_tokens": 300, "output_tokens": 450}
if fmt == "hermes":
    emit({"type": "system", "session_id": sid})
elif fmt == "claude":
    emit({"type": "system", "subtype": "init", "session_id": sid, "tools": ["Bash", "Read"]})
elif fmt == "codex":
    emit({"type": "thread.started", "thread_id": sid})
    emit({"type": "turn.started"})
else:
    emit({"type": "session", "id": sid})
for n, (name, args, result) in enumerate(calls):
    call = "call_%d" % n
    output = json.dumps(result) if result else "notebook text"
    error = bool(result and result["exit_code"])
    if fmt == "hermes":
        emit({"type": "tool_use", "name": name, "tool_call_id": call, "input": args})
        emit({"type": "tool_result", "name": name, "tool_call_id": call, "output": output, "is_error": error}, 4000)
    elif fmt == "claude":
        tool = {"name": "Bash", "input": args} if name == "terminal" else {"name": "Read", "input": {"file_path": args["path"]}}
        emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": call, **tool}]}, "session_id": sid})
        emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": call, "content": output,
              "is_error": error}]}, "session_id": sid})
    elif fmt == "codex":
        if name == "terminal":
            emit({"type": "item.completed", "item": {"id": call, "type": "command_execution", "command": args["command"],
                  "aggregated_output": output, "exit_code": result["exit_code"], "status": "completed"}})
    else:
        emit({"type": "tool_call", "id": call, "name": name, "input": args})
        emit({"type": "tool_result", "id": call, "output": output, **({"exit_code": result["exit_code"]} if result else {})})
    if n == 2:
        if fmt == "hermes":
            print("⟳ compacting context…", flush=True)
        elif fmt == "claude":
            # Claude Code marks a compaction in stream-json with a compact_boundary system message.
            emit({"type": "system", "subtype": "compact_boundary", "session_id": sid,
                  "compact_metadata": {"trigger": "auto", "pre_tokens": 1200}})
        compaction = trial / "scripted-compaction"
        if compaction.is_file() and store == "claude":
            # Like Claude Code: the summary is a transcript entry marked isCompactSummary (no fallback marker).
            with (folder / (sid + ".jsonl")).open("a") as log:
                log.write(json.dumps({"type": "user", "isCompactSummary": True, "uuid": str(uuid.uuid4()),
                                      "sessionId": sid, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                                      "message": {"role": "user", "content": "This session is being continued from a "
                                                  "previous conversation. Summary of the work so far."}}) + "\n")
        elif compaction.is_file():
            # Like Hermes: the summary (or its deterministic fallback) is a message in the session database.
            kind = compaction.read_text().strip() or "summary"
            text = ("[CONTEXT COMPACTION] deterministic fallback: the summarizer did not answer\n\n## Goal\n"
                    "Recovered from a deterministic fallback because the LLM context summarizer was unavailable."
                    if kind == "fallback"
                    else "[CONTEXT COMPACTION] summary of the work so far")
            db = sqlite3.connect(home / "state.db")
            db.execute("INSERT INTO messages VALUES(?,?,?)", (sid + "-compaction", text, time.time()))
            db.commit()
            db.close()
        if pause.is_file():
            time.sleep(float(pause.read_text() or 0))
code = 1 if failed else 0
if fmt == "hermes":
    # Hermes-native telemetry keys (daw.hermes.parse reads input, cache_read and output).
    emit({"type": "result", "exit_code": code, "text": answer,
          "tokens": {"input": 1200, "cache_read": 300, "output": 450}})
elif fmt == "claude":
    emit({"type": "result", "subtype": "error_during_execution" if failed else "success", "is_error": failed,
          "result": answer, "session_id": sid, "num_turns": len(calls) + 1,
          "usage": {"input_tokens": 900, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 300, "output_tokens": 450}})
elif fmt == "codex":
    emit({"type": "item.completed", "item": {"id": "msg", "type": "agent_message", "text": answer}})
    emit({"type": "turn.failed" if failed else "turn.completed", "usage": {**usage, "reasoning_output_tokens": 0}})
else:
    emit({"type": "message", "text": answer})
    emit({"type": "error", "message": "scripted failure"} if failed else {"type": "turn_completed", "usage": usage})
sys.exit(code)
'''


def install(path):
    """Write the scripted harness as an executable for this interpreter."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n" + SCRIPT)
    path.chmod(0o755)
    return str(path)


def sniff(path):
    """The stream's format from its first event."""
    if Path(path).exists():
        with Path(path).open("rb") as stream:
            for raw in stream:
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    kind = event.get("type")
                    if kind == "system":
                        return "claude" if event.get("subtype") == "init" else "hermes"
                    return {"thread.started": "codex", "session": "jsonl"}.get(kind, "hermes")
    return "hermes"


PARSERS = {"hermes": hermes.ADAPTER.parse, "claude": claude.parse, "codex": codex.ADAPTER.parse, "jsonl": mcp.parse}


class ScriptedAdapter(Adapter):
    """The deterministic test harness as its own adapter; `harness_options.stream_format` picks the stream."""
    name = "scripted"
    home_dir = ".scripted"
    default_model = "scripted"
    default_provider = "none"
    compaction_store = "agent-state/state.db"  # the stand-in keeps a Hermes-like session database

    def reports_compactions(self, config):
        # The Hermes- and Claude-format stand-in streams mark compactions, as those harnesses do.
        return (config.get("harness_options") or {}).get("stream_format", "hermes") in ("hermes", "claude")

    def stage(self, trial, home, config):
        fmt = (config.get("harness_options") or {}).get("stream_format", "hermes")
        if fmt not in PARSERS:
            raise DawError("invalid_harness_options", f"stream_format is one of {', '.join(PARSERS)}")
        return None

    def command(self, executable, trial, config, *, resume=None, fork=False):
        if fork:
            raise DawError("harness_fork_unsupported", "scripted")
        fmt = (config.get("harness_options") or {}).get("stream_format", "hermes")
        argv = [executable, "--stream-format", fmt, "--home", str(self.home(trial))]
        return argv + (["--resume", resume] if resume else [])

    def snapshot(self, home, destination):
        return hermes.ADAPTER.snapshot(home, destination)

    def session_exists(self, home, identity):
        hermes.ADAPTER.session_exists(home, identity)

    def parse(self, path):
        return PARSERS[sniff(path)](Path(path))


ADAPTER = ScriptedAdapter()
