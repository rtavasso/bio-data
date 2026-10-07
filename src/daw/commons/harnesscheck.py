"""Live-receipt harness checks (spec v2 V8): one minimal scripted assignment, resume included, per harness.

`bio commons harness-check --harness codex|claude|hermes` builds a throwaway commons, adds one agent on the
named harness, and delivers two operator assignments through the ordinary runtime (`community_runtime.dispatch`,
the same path every delivery takes):

1. turn 1 gives a fresh key phrase and asks for a one-line reply containing it (no tools, no analysis);
2. turn 2 resumes the saved native conversation and asks for the phrase from the previous turn.

The receipt is compact and contains no paths, prompts, answers or credentials: the harness and its reported
version, per turn the request state, exit code, clocks, whether the answer contains the key phrase (and the
answer's sha256), token telemetry as the adapter parsed it, compaction hygiene (`daw.commons.hygiene`), and
for the resume whether turn 2 continued the session turn 1 saved (same native session id, the adapter's
resume argument in the launch line). `verdict` is `pass` only when both turns completed, the session resumed
and turn 2 recalled the phrase.

Live runs need `DAW_LIVE=1`, the harness installed (`--executable` or the adapter's default on PATH) and its
credentials (the adapter's auth file variable or API key); a live receipt is written to
`docs/v3/receipts/harness-check-<harness>.json`. `--scripted` runs the same code path against the scripted
stand-in executable (`daw.harness.scripted`), which speaks each harness's stream and session protocol offline;
its receipt says `live: false` and can only be written to an explicit `--output` outside `docs/v3/receipts/`,
so a stand-in result is never filed as a live receipt.
"""
import hashlib
import os
import shutil
import subprocess
import uuid
from contextlib import nullcontext
from pathlib import Path

from daw.util import DawError, canonical, now, read_json

HARNESSES = ("codex", "claude", "hermes")
FORMAT = "colloquy.harness-check/1"
RECEIPTS = Path(__file__).resolve().parents[3] / "docs" / "v3" / "receipts"
RESUME_FLAGS = {"codex": ("resume",), "claude": ("--resume",), "hermes": ("--resume",)}
TURN_ONE = ("Harness check, turn 1 of 2. Assignment key phrase: {phrase}. Do not run tools, analyses or searches. "
            "Reply with exactly one line that contains the key phrase.")
TURN_TWO = ("Harness check, turn 2 of 2, in the same conversation. Do not run tools or searches. Reply with exactly "
            "one line that contains the assignment key phrase you were given in turn 1.")


def default_output(harness):
    return RECEIPTS / f"harness-check-{harness}.json"


def _version(executable):
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        return f"unavailable ({type(error).__name__})"
    text = (result.stdout or result.stderr).strip().splitlines()
    return text[0][:200] if text else f"unavailable (exit {result.returncode})"


def _turn(board, request, phrase, harness):
    from daw import harness as harnesses
    from daw.commons import hygiene, metrics
    request = board.one("SELECT * FROM request WHERE id=?", (request["id"],))
    attempt = board.one("SELECT * FROM attempt WHERE request=? ORDER BY created DESC LIMIT 1", (request["id"],))
    folder = Path(board.root) / attempt["path"] if attempt else None
    execution = read_json(folder / "execution.json") if folder and (folder / "execution.json").is_file() else {}
    state = read_json(folder / "state-receipt.json") if folder and (folder / "state-receipt.json").is_file() else {}
    answer = board.show(request["answer"])["content"].get("body") or "" if request["answer"] else ""
    parsed = harnesses.get(harness).parse(folder / "events.jsonl") if folder else {"usage": None, "turns_completed": 0}
    tokens, note = metrics.token_usage(parsed)
    argv = execution.get("argv") or []
    argv = argv if isinstance(argv, list) else str(argv).split()
    return {"state": request["state"], "returncode": execution.get("returncode"),
            "wall_seconds": execution.get("wall_seconds"), "monotonic_seconds": execution.get("monotonic_seconds"),
            "answer_contains_phrase": phrase in answer, "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
            "session": state.get("session"), "turns_completed": parsed.get("turns_completed"),
            "tokens": tokens, "tokens_note": note,
            "resume_argument": any(flag in argv for flag in RESUME_FLAGS.get(harness, ())),
            "hygiene": hygiene.run_hygiene(folder, harness) if folder else None}


def run(harness, workdir, *, executable=None, model=None, scripted=False):
    """Run the two-turn check in a fresh commons at `workdir` and return the receipt (not written)."""
    from daw import harness as harnesses
    from daw.commons import demo
    from daw.community import Community
    from daw.community_runtime import add_agent, dispatch
    if harness not in HARNESSES:
        raise DawError("unknown_harness", f"use one of {', '.join(HARNESSES)}")
    adapter = harnesses.get(harness)
    workdir = Path(workdir).expanduser().resolve()
    if workdir.exists() and any(workdir.iterdir()):
        raise DawError("workdir_not_empty", str(workdir))
    if not scripted:
        if os.environ.get("DAW_LIVE") != "1":
            raise DawError("live_opt_in_required", "set DAW_LIVE=1 to run a live harness check (or pass --scripted)")
        executable = shutil.which(executable or adapter.default_executable)
        if not executable:
            raise DawError("harness_not_installed", f"{harness}: put its CLI on PATH or pass --executable")
    phrase = "COLLOQUY-CHECK-" + uuid.uuid4().hex[:12].upper()
    started = now()
    board = Community.create(workdir)
    try:
        demo._no_reserve(board.library.root)  # a throwaway commons: no disk reserve (as the demo)
        from daw.catalog import Workspace
        board.library.close()
        board.library = Workspace(board.root / "library")
        context = demo.scripted_runtime(workdir) if scripted else nullcontext((executable, None))
        with context as (launch, answers):
            agent = add_agent(board, f"check-{harness}", harness=harness, model=model)
            turns = []
            for n, text in enumerate((TURN_ONE.format(phrase=phrase), TURN_TWO), 1):
                request = board.ask(agent["id"], "operator", text, request_key=f"harness-check-{n}")
                if scripted:  # the stand-in answers from a file: it recalls nothing, it only exercises the protocol
                    post = board.one("SELECT post FROM request WHERE id=?", (request["id"],))["post"]
                    (answers / f"{post}.md").write_text(f"Turn {{turns}}: {phrase}")
                try:
                    dispatch(board, request["id"], launch)
                except DawError as error:
                    turns.append({"state": "error", "error": error.reason})
                    break
                turns.append(_turn(board, request, phrase, harness))
            version = "scripted stand-in" if scripted else _version(executable)
            sessions = [t.get("session") for t in turns]
    finally:
        board.close()
    resumed = len(turns) == 2 and all(t.get("state") == "completed" for t in turns) and sessions[0] is not None \
        and sessions[0] == sessions[1]
    failures = []
    if len(turns) < 2 or any(t.get("state") != "completed" for t in turns):
        failures.append("a turn did not complete")
    if not resumed:
        failures.append("turn 2 did not continue the session saved by turn 1")
    if len(turns) == 2 and not turns[1].get("resume_argument"):
        failures.append("turn 2 was not launched with the harness's resume argument")
    if len(turns) == 2 and not turns[1].get("answer_contains_phrase"):
        failures.append("turn 2's answer does not contain the key phrase from turn 1")
    return {"format": FORMAT, "harness": harness, "live": not scripted, "scripted_stand_in": scripted,
            "executable": Path(executable).name if executable and not scripted else "scripted", "version": version,
            "model": model or adapter.default_model, "started": started, "finished": now(),
            "phrase_sha256": hashlib.sha256(phrase.encode()).hexdigest(), "turns": turns,
            "resume": {"same_session": resumed, "argument_used": bool(len(turns) == 2 and turns[1].get("resume_argument"))},
            "verdict": "pass" if not failures else "fail", "failures": failures,
            "note": ("Scripted stand-in: exercises the adapter, stream parser and resume path offline. It is not a "
                     "live receipt." if scripted else "Live harness check through community_runtime.dispatch."),
            "limitations": ["Two short turns: this checks launch, stream parsing, token telemetry and resume, not "
                            "research behaviour.",
                            "The key-phrase recall is a property of the harness's saved conversation; a harness that "
                            "re-reads its board inbox could also find it."]}


def write(receipt, output=None):
    """Write a receipt. Scripted receipts need an explicit output outside docs/v3/receipts (never filed as live)."""
    if receipt["scripted_stand_in"]:
        if output is None:
            raise DawError("output_required", "a scripted check is not a live receipt: pass --output")
        if Path(output).expanduser().resolve().parent == RECEIPTS.resolve():
            raise DawError("scripted_receipt_refused", "docs/v3/receipts holds live receipts only")
    path = Path(output).expanduser() if output else default_output(receipt["harness"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(receipt) + b"\n")
    return str(path)
