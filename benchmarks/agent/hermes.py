"""Stock Hermes CLI integration. No replacement agent loop or model dependency."""
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from daw.util import digest, file_hash, read_json, write_json


STATE_DIRS = ("memories", "skills")
STATE_FILES = ("state.db",)


def safe_files(root):
    root = Path(root)
    if root.is_symlink():
        raise ValueError("learning state root must not be a symlink")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"learning state refuses symlink: {path.name}")
        if path.is_file():
            yield path


def state_hashes(root):
    return {str(p.relative_to(root)): file_hash(p) for p in safe_files(root)}


def live_state_hashes(home):
    files = {}
    for name in STATE_DIRS:
        files.update({name + "/" + key: value for key, value in state_hashes(home / name).items()})
    for name in STATE_FILES:
        if (home / name).is_symlink():
            raise ValueError("session database must not be a symlink")
        if (home / name).exists():
            files[name] = file_hash(home / name)
    return files


def snapshot_state(home, destination):
    """Allowlisted scientific session state; never copy auth, .env or global config."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name in STATE_DIRS:
        source = home / name
        if source.is_symlink():
            raise ValueError("learning directory must not be a symlink")
        if source.exists():
            for path in safe_files(source):
                target = destination / name / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    source = home / "state.db"
    if source.is_symlink():
        raise ValueError("session database must not be a symlink")
    if source.exists():
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(destination / "state.db")) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("invalid Hermes session database")
                # Keep the exported database self-contained and read-stable.
                dst.execute("PRAGMA journal_mode=DELETE")
    return state_hashes(destination)


def restore_state(checkpoint, home):
    checkpoint = Path(checkpoint).resolve()
    receipt = read_json(checkpoint / "checkpoint.json")
    if receipt.get("format_version") != 1 or not receipt.get("restorable"):
        raise ValueError("checkpoint is not restorable")
    source = checkpoint / "agent"
    if state_hashes(source) != receipt["agent_files"]:
        raise ValueError("learning checkpoint changed")
    for name in receipt["agent_files"]:
        path = Path(name)
        if path.parts[0] not in STATE_DIRS and name not in STATE_FILES:
            raise ValueError("unexpected file in learning checkpoint")
        target = home / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / path, target)
    return file_hash(checkpoint / "checkpoint.json")


def prepare_home(trial, model, effort, provider, checkpoint=None, skills=True):
    home = trial / ".hermes"
    home.mkdir(mode=0o700)
    (home / ".no-bundled-skills").touch()
    parent = restore_state(checkpoint, home) if checkpoint else None
    for name in STATE_DIRS:
        (home / name).mkdir(exist_ok=True)
    # JSON is also valid YAML. No additional dependency in the offline evaluator.
    config = {
        "_config_version": 12,
        "model": {"default": model, "provider": provider},
        "agent": {"reasoning_effort": effort, "max_turns": 0},
        "terminal": {"backend": "local", "cwd": str(trial)},
        "memory": {"memory_enabled": True, "user_profile_enabled": False},
        "skills": {"project_discovery": skills, "trusted_project_dirs": [str(trial)] if skills else [],
                   "create_dir": str(home / "skills")},
        # One-shot CLI background-review threads need not finish before exit.
        # Foreground consolidation uses stock memory/skill tools before final answer.
        "auxiliary": {"background_review": {"enabled": False}},
        "curator": {"enabled": False},
        "display": {"interface": "cli"},
    }
    write_json(home / "config.yaml", config)
    hashes = snapshot_state(home, trial.parent / "learning-before")
    write_json(trial.parent / "learning-baseline.json", {"files": hashes, "parent_checkpoint": parent,
        "policy": "foreground native memory/skills; automatic background review disabled"})
    return {"config_sha256": file_hash(home / "config.yaml"), "state_sha256": digest(hashes),
            "live_state_sha256": digest(live_state_hashes(home)),
            "parent_checkpoint": parent}


def command(executable, trial, model, provider, public=False):
    toolsets = "terminal,file,skills,memory,session_search" + (",web" if public else "")
    return [executable, "chat", "--query-file", "-", "--oneshot", "--format", "stream-json",
            "--model", model, "--provider", provider, "--toolsets", toolsets]


def environment(base, trial):
    # Prevent another Hermes profile's runtime configuration from leaking into a trial.
    result = {k: v for k, v in base.items() if not k.startswith("HERMES_")}
    result.update(HERMES_HOME=str(trial / ".hermes"), HERMES_CWD=str(trial),
                  HERMES_INTERACTIVE="0", PYTHONUNBUFFERED="1")
    if auth := base.get("BIO_HERMES_AUTH_FILE"):
        source = Path(auth).expanduser().resolve(strict=True)
        if source.is_relative_to(trial.parents[2]):
            raise ValueError("Hermes credentials must live outside evaluation artifacts")
        target = trial / ".hermes/auth.json"
        if target.exists() or target.is_symlink():
            raise ValueError("unexpected auth file in prepared Hermes home")
        target.symlink_to(source)
    # Authentication is resolved by the stock provider; never put tokens in manifests.
    return result


def parse(path):
    """Retain native line references; conservatively adapt tools for existing reports."""
    events, malformed, items, errors, sessions, results = [], [], [], [], [], []
    pending = {}
    if path.exists():
        for line, raw in enumerate(path.read_bytes().splitlines(), 1):
            try:
                event = json.loads(raw)
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ValueError("invalid event")
            except (ValueError, UnicodeDecodeError):
                malformed.append(line)
                continue
            events.append({"line": line, "event": event})
            kind = event["type"]
            if kind == "system" and event.get("session_id"):
                sessions.append(event["session_id"])
            elif kind == "tool_use":
                name = event.get("name", "unknown")
                item = {"line": line, "type": "command_execution" if name == "terminal" else name,
                        "name": name, "status": "in_progress", "exit_code": None,
                        "input": event.get("input") if isinstance(event.get("input"), dict) else {}}
                item["command"] = item["input"].get("command", "")
                items.append(item)
                matches = pending.setdefault(event.get("tool_call_id", name), [])
                if not event.get("tool_call_id") and matches:
                    for ambiguous in [*matches, item]:
                        ambiguous["ambiguous_result"] = True
                matches.append(item)
            elif kind == "tool_result":
                matches = pending.get(event.get("tool_call_id", event.get("name")), [])
                if matches:
                    item = matches.pop(0)
                    item.update(status="completed", aggregated_output=event.get("output", ""), result_line=line)
                    # is_error=False does not prove shell exit 0. Only explicit results do.
                    try:
                        output = json.loads(event.get("output", ""))
                    except (ValueError, TypeError):
                        output = {}
                    if item.get("ambiguous_result"):
                        continue  # Parallel same-name calls without IDs cannot be safely attributed.
                    if isinstance(output, dict) and type(output.get("exit_code")) is int:
                        item["exit_code"] = output["exit_code"]
                    elif event.get("is_error"):
                        item["exit_code"] = 1
            elif kind == "result":
                results.append(event)
                items.append({"line": line, "type": "agent_message", "text": event.get("text", "")})
                if event.get("exit_code") != 0 or event.get("error"):
                    errors.append({"line": line, "event": event})
    successful = [r for r in results if r.get("exit_code") == 0 and not r.get("error")]
    mapping = {"input_tokens": "input", "cached_input_tokens": "cache_read", "output_tokens": "output"}
    usage = None
    if results:
        usage = {key: sum(r["tokens"][native] for r in results)
                 if all(type(r.get("tokens", {}).get(native)) is int for r in results) else None
                 for key, native in mapping.items()}
        usage["reasoning_output_tokens"] = None
    return {"events": events, "items": items, "malformed_lines": malformed, "turns_completed": len(successful),
            "errors": errors, "usage": usage, "thread_ids": sessions,
            "limitations": ["Hermes stream tool outputs are capped upstream at 5000 characters; inspect state.db for full messages.",
                            "Token fields are provider-reported; upstream may emit zero for unavailable telemetry."]}


def finish(folder, execution):
    from daw.catalog import Workspace
    trial = folder / "trial"
    parsed = parse(folder / "events.jsonl")
    answers = [i["text"] for i in parsed["items"] if i.get("type") == "agent_message"]
    if answers:
        (folder / "final.md").write_text(answers[-1])
    checkpoint = folder / "checkpoint"
    checkpoint.mkdir()
    files = snapshot_state(trial / ".hermes", checkpoint / "agent")
    ws = Workspace(trial / "workspace")
    try:
        with ws.writer():
            ws.backup(checkpoint / "workspace")
    finally:
        ws.close()
    # Operational lock creation on later reads must not invalidate the snapshot.
    (checkpoint / "workspace/.writer.lock").touch()
    before = read_json(folder / "learning-baseline.json")["files"]
    receipt = {"format_version": 1, "restorable": True,
               "completed": execution["state"] == "exited" and bool(parsed["turns_completed"]) and not parsed["errors"],
               "agent_files": files, "workspace_files": state_hashes(checkpoint / "workspace"),
               "parent_checkpoint": read_json(folder / "learning-baseline.json")["parent_checkpoint"],
               "changes": {"added": sorted(files.keys() - before.keys()), "removed": sorted(before.keys() - files.keys()),
                           "modified": sorted(k for k in files.keys() & before.keys() if files[k] != before[k])},
               "learning_policy": "foreground writes; background review disabled; retention is not proof of learning quality"}
    write_json(checkpoint / "checkpoint.json", receipt)
    return receipt
