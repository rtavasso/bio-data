"""Replication that executes, under one explicit carve-out (M6.3, spec v2 C6).

The carve-out (AGENTS.md): a replication task may execute only the code blobs named in the fetched
derivation, after hash verification, through run_analysis.py (the research skill's helper, driven by
`.agents/skills/bio-research/scripts/replicate.py`), inside a sandbox with egress off. Any other execution
of fetched code remains forbidden.

This module holds the platform side of that carve-out; it never executes anything itself.

- `originals(board, subject)`: the artifacts a replication request is about (an artifact subject; a post's
  published evidence; a claim's or frontier item's artifact pointers).
- `producers(board, artifacts)`: participants whose own workspace produced one of them (a `produced`
  registration link, or a registration without any question link). A fork that inherited that workspace
  holds the same links, so it counts as a producer too. `refuse_producer` raises
  `replication_target_produced_original`; commission, promotion, typed assignment and dispatch call it.
- The receipt gate: a replica counts only when the replicating agent's workspace records a
  `replication_execution` work event (written by replicate.py, or by hand with `bio work event`) whose
  `receipt_blob` is a run_analysis.py receipt that ran a producer whose sha256 is one of the derivation's
  code blobs, left it unchanged, exited 0, completed, and wrote an output whose sha256 is the replica's
  output blob. Since v3 B3 the receipt must also be captured: a terminal call to run_analysis.py (directly,
  with a `--receipt` path naming the cited receipt, or through replicate.py) in the delivery's own stream
  printed an `analysis_executed` line whose receipt path is the one the event cites (`receipt_path`) and
  whose sha256 is `receipt_blob`. A hand-written receipt has no such call. Otherwise the outcome is
  `no_execution_receipt` and nothing is confirmed. The receipt's input sha256s (run_analysis.py --input)
  must equal the derivation's inputs, in order; a captured run on other inputs is `inputs_differ`, which
  confirms nothing and never becomes a correction against the original. Receipts are read from the
  agent's workspace through `Archive` (read-only); the gate is structural, not a scientific verdict.
  Limitation: the stream is the agent's own terminal output; one `analysis_executed` line per call is
  required, but a deliberate shell forgery of that line is not excluded here.
- Sandbox: only a sandboxed dispatch confirms or corrects. A replication delivered without a sandbox
  (local single-user mode, `replication_unsandboxed`) is `local_rehearsal`: its byte comparison is kept as
  `rehearsal` and nothing is posted (`dispatch_sandboxed`).
- `SYSTEM_PARTICIPANT`: confirmations and mismatch posts and marks are platform records authored by the
  `replication` system participant, citing the agent's receipt; agents sign only what they wrote.
"""
import json
import os
from pathlib import Path, PurePosixPath

from daw.commons.archive import Archive
from daw.util import DawError, read_json

EXECUTION_EVENT = "replication_execution"
SYSTEM_PARTICIPANT = "replication"
RECEIPT_FIELDS = ("code_sha256", "producer", "exit_code", "started", "finished")
# The receipt-gate problem that classifies a captured, complete run as `inputs_differ` (not a mismatch).
INPUTS_DIFFER = "inputs_differ"
NOT_CAPTURED = "receipt_not_in_captured_stream"


def originals(board, subject):
    """Artifact ids a replication of `subject` ({kind, id}) re-executes, in recorded order."""
    if not subject or not subject.get("id"):
        return []
    kind, identity = subject.get("kind"), subject["id"]
    if identity.startswith("artifact_"):
        return [identity]
    if identity.startswith("post_"):
        return list(dict.fromkeys((board.show(identity)["content"].get("evidence") or {}).get("artifacts") or []))
    table = "claim" if identity.startswith("claim_") else "frontier_item" if kind == "frontier_item" else None
    row = board.one(f"SELECT pointers FROM {table} WHERE id=?", (identity,)) if table else None
    pointers = json.loads(row["pointers"] or "[]") if row else []
    return list(dict.fromkeys(p["id"] for p in pointers
                              if isinstance(p, dict) and p.get("kind") == "artifact" and isinstance(p.get("id"), str)))


def producers(board, artifacts):
    """{participant id: [artifact ids it produced]} for participants whose own workspace produced any of them."""
    artifacts = sorted(set(artifacts))
    found = {}
    if not artifacts:
        return found
    marks = ",".join("?" * len(artifacts))
    with Archive(board.root) as view:
        for agent in view.rows("SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY created,id"):
            try:
                ws = view.workspace(agent["id"])
                held = {r["id"] for r in ws.rows(f"SELECT id FROM artifact WHERE id IN ({marks})", artifacts)}
                links = ws.rows(f"SELECT artifact_id,relationship FROM question_artifact WHERE artifact_id IN ({marks})",
                                artifacts)
            except DawError:
                continue  # no catalog: this participant holds nothing
            relations = {}
            for link in links:
                relations.setdefault(link["artifact_id"], set()).add(link["relationship"])
            produced = sorted(a for a in held if "produced" in relations.get(a, set()) or not relations.get(a))
            if produced:
                found[agent["id"]] = produced
    return found


def refuse_producer(board, target, subject):
    """Refuse a replication whose target produced (or inherited the production of) an original artifact."""
    produced = producers(board, originals(board, subject)).get(target)
    if produced:
        raise DawError("replication_target_produced_original",
                       f"{target} produced {', '.join(produced)} (forks inherit their parent's workspace); "
                       "a replication needs a participant that did not produce the original")


# ---- the receipt gate ---------------------------------------------------------------------------

def check_receipt(ws, receipt_blob, code_blobs, output_blob, input_blobs):
    """(summary, problems) for one stored run_analysis.py receipt against a derivation and a replica's bytes."""
    from daw.profiles import verify_object
    try:
        receipt = json.loads(verify_object(ws, receipt_blob).read_bytes())
    except DawError as error:
        return None, [f"receipt_{error.reason}"]
    except (ValueError, UnicodeDecodeError):
        return None, ["receipt_not_json"]
    if not isinstance(receipt, dict) or receipt.get("version") != 1 or not isinstance(receipt.get("outputs"), list):
        return None, ["not_a_run_analysis_receipt"]
    problems = []
    if receipt.get("code_sha256") not in set(code_blobs):
        problems.append("producer_not_a_derivation_code_blob")
    if receipt.get("exit_code") != 0:
        problems.append("execution_failed")
    if receipt.get("code_unchanged") is not True:
        problems.append("code_changed_during_run")
    if receipt.get("complete") is not True:
        problems.append("receipt_incomplete")
    if not any(isinstance(o, dict) and o.get("sha256") == output_blob and o.get("written") is True
               for o in receipt["outputs"]):
        problems.append("replica_bytes_not_written_by_run")
    # v3 B3: the inputs the run read (run_analysis.py --input), in derivation order. A receipt without them
    # (written before B3, or without --input) confirms nothing.
    recorded = receipt.get("inputs")
    hashes = ([i.get("sha256") for i in recorded if isinstance(i, dict)]
              if isinstance(recorded, list) and all(isinstance(i, dict) for i in recorded) else None)
    if hashes is None:
        problems.append("receipt_records_no_inputs")
    elif hashes != list(input_blobs):
        problems.append(INPUTS_DIFFER)
    elif hashes and receipt.get("inputs_unchanged") is not True:
        problems.append("inputs_changed_during_run")
    producer = str(receipt.get("producer") or "")
    summary = {"receipt_blob": receipt_blob, **{k: receipt.get(k) for k in RECEIPT_FIELDS},
               # Relative to the agent's workspace: host paths stay out of board records.
               "producer": producer[producer.index("questions/"):] if "questions/" in producer else Path(producer).name,
               "inputs": hashes, "outputs": [{"sha256": o.get("sha256"), "written": o.get("written")}
                                             for o in receipt["outputs"] if isinstance(o, dict)]}
    return summary, problems


def _tool_texts(output):
    """A terminal call's output text, and the text inside a harness's JSON result wrapper (Hermes)."""
    texts = [output] if isinstance(output, str) else []
    try:
        wrapped = json.loads(output) if texts else None
    except ValueError:
        wrapped = None
    if isinstance(wrapped, dict) and isinstance(wrapped.get("output"), str):
        texts.append(wrapped["output"])
    return texts


def _same_file(printed, named):
    """Does a path run_analysis.py printed (resolved) name the file a path argument named (maybe relative)?"""
    path, name = PurePosixPath(printed), PurePosixPath(named)
    if name.is_absolute():
        return path in (name, PurePosixPath(os.path.realpath(named)))
    parts = tuple(p for p in name.parts if p != ".")
    return bool(parts) and ".." not in parts and path.parts[-len(parts):] == parts


def stream_executions(parsed):
    """`analysis_executed` result lines of the delivery's captured terminal calls to run_analysis.py (directly,
    whose `--receipt` argument must name the printed receipt, or through replicate.py, which echoes the line).
    A call whose output carries more than one such line is ambiguous and not counted."""
    from daw.commons.records import _printed, _receipt_argument
    found = []
    for item in (parsed or {}).get("items", []):
        command = item.get("command") if isinstance(item.get("command"), str) else ""
        direct = "run_analysis.py" in command
        if item.get("name") != "terminal" or not (direct or "replicate.py" in command):
            continue
        named = _receipt_argument(command) if direct else None
        lines = [p for text in _tool_texts(item.get("aggregated_output") or item.get("output")) for p in _printed(text)]
        lines = list({json.dumps(p, sort_keys=True): p for p in lines}.values())  # wrapper and inner text agree
        if (direct and not named) or len(lines) != 1:
            continue
        receipt, sha = lines[0].get("receipt"), lines[0].get("sha256")
        if not isinstance(receipt, str) or not isinstance(sha, str) or (named and not _same_file(receipt, named)):
            continue
        found.append({"receipt": receipt, "sha256": sha, "line": item.get("line"),
                      "helper": "run_analysis.py" if direct else "replicate.py"})
    return found


def captured(event, stream):
    """The captured call for an execution event: its printed receipt path is the one the event cites
    (`receipt_path`, relative to the event's question or absolute) and its printed sha256 is `receipt_blob`."""
    payload = event["payload"]
    cited = payload.get("receipt_path")
    if not isinstance(cited, str) or not cited.strip():
        return None
    name = PurePosixPath(cited)
    expected = cited if name.is_absolute() else str(PurePosixPath("questions", event["question_id"], name))
    for call in stream:
        if call["sha256"] == payload["receipt_blob"] and _same_file(call["receipt"], expected):
            return {"line": call["line"], "helper": call["helper"]}
    return None


def dispatch_sandboxed(root, run):
    """True only when the run's dispatch recorded a sandbox (`runs/<run>/sandbox.json`, sandboxed: true)."""
    path = Path(root) / "runs" / str(run or "") / "sandbox.json"
    try:
        return bool(run) and path.is_file() and read_json(path).get("sandboxed") is True
    except (OSError, ValueError, AttributeError):
        return False


def execution_events(ws, since=None):
    """`replication_execution` work events in an agent workspace (optionally created at or after `since`)."""
    rows = ws.rows("SELECT id,question_id,body_blob,created FROM work_event WHERE kind=? AND created>=? "
                   "ORDER BY created,id", (EXECUTION_EVENT, since or ""))
    events = []
    for row in rows:
        try:
            payload = json.loads(ws.blob_path(row["body_blob"]).read_bytes())
        except (DawError, OSError, ValueError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("receipt_blob"), str):
            events.append({**row, "payload": payload})
    return events


def _candidate(ws, event, code_blobs, output_blob, input_blobs, stream):
    summary, issues = check_receipt(ws, event["payload"]["receipt_blob"], code_blobs, output_blob, input_blobs)
    call = captured(event, stream) if summary else None
    if summary and not call:
        issues = issues + [NOT_CAPTURED]
    return ({**summary, "event": event["id"], "question": event["question_id"], "stream": call}
            if summary else None), issues


def receipt_for(ws, events, code_blobs, output_blob, input_blobs, stream):
    """(the first valid receipt for these bytes, problems of every candidate, a captured complete receipt whose
    only problem is that its inputs differ from the derivation's, or None); candidates are execution events."""
    problems, differing = [], None
    for event in events:
        summary, issues = _candidate(ws, event, code_blobs, output_blob, input_blobs, stream)
        if summary and not issues:
            return summary, [], None
        if summary and issues == [INPUTS_DIFFER] and differing is None:
            differing = summary
        problems.append({"event": event["id"], "receipt_blob": event["payload"]["receipt_blob"], "problems": issues})
    return None, problems or [{"problems": ["no_replication_execution_recorded"]}], differing


def reverify(board, agent, run, receipt, code_blobs, input_blobs, output_blob):
    """Re-check a receipt recorded in a task outcome (read-only): the stored receipt against the derivation and
    the bytes, and its execution event against the run's captured stream, re-parsed from `runs/<run>`."""
    from daw.harness import for_agent
    if not isinstance(receipt, dict) or not receipt.get("receipt_blob") or not receipt.get("event"):
        return False
    stream = stream_executions(for_agent(agent).parse(Path(board.root) / "runs" / str(run) / "events.jsonl"))
    with Archive(board.root) as view:
        ws = view.workspace(agent["id"])
        if ws is None:
            return False
        events = [e for e in execution_events(ws) if e["id"] == receipt["event"]]
        if not events or events[0]["payload"]["receipt_blob"] != receipt["receipt_blob"]:
            return False
        summary, problems = _candidate(ws, events[0], code_blobs, output_blob, input_blobs, stream)
    return bool(summary) and not problems


def receipt_line(receipt):
    inputs = ", ".join(f"`{h}`" for h in receipt.get("inputs") or []) or "none"
    stream = receipt.get("stream") or {}
    return (f"run_analysis receipt `{receipt['receipt_blob']}` (workspace event {receipt.get('event')}; captured by "
            f"{stream.get('helper', 'run_analysis.py')} at events.jsonl line {stream.get('line')}): producer "
            f"code sha256 `{receipt['code_sha256']}`, input sha256 {inputs}, exit code {receipt['exit_code']}, "
            f"started {receipt.get('started')}, finished {receipt.get('finished')}")


# ---- requests from people and the badge people can trust (spec v3 V14) --------------------------

DEFAULT_BUDGET = {"minutes": 60}


def settings(root):
    """The commons' replication policy (`commons.toml [replication]`): `default_budget` of a person's replication
    request (default DEFAULT_BUDGET) and `accept_outside` (whether people from outside this commons may request
    replications; listed in directory entries). Reads the file only."""
    import tomllib

    from daw.commons.tasks import normalize_budget
    path = Path(root) / "commons.toml"
    try:
        configured = tomllib.loads(path.read_text()).get("replication", {}) if path.is_file() else {}
    except tomllib.TOMLDecodeError as error:
        raise DawError("invalid_commons_config", str(error)) from error
    if not isinstance(configured, dict) or set(configured) - {"default_budget", "accept_outside"}:
        raise DawError("invalid_commons_config", "[replication] takes default_budget and accept_outside")
    accept = configured.get("accept_outside", False)
    if not isinstance(accept, bool):
        raise DawError("invalid_commons_config", "[replication] accept_outside is true or false")
    return {"default_budget": normalize_budget(configured.get("default_budget")) or dict(DEFAULT_BUDGET),
            "accept_outside": accept}


def _system_id(view):
    row = view.one("SELECT id FROM agent WHERE name=? AND kind='system'", (SYSTEM_PARTICIPANT,))
    return row["id"] if row else None


def badge(view, artifact, *, vis=None):
    """The replication badge of a library artifact: replicated only when a confirmation by the replication
    participant shows (1) a different participant from every producer, (2) a captured execution in a sandboxed
    dispatch, (3) receipt inputs equal to the derivation's recorded inputs and (4) output bytes identical to the
    artifact's, each re-read from records now and each a link. Other replication outcomes on the artifact are
    listed as `attempts`. Read-only; a confirmation on a hidden post is withheld and counts nothing."""
    from daw.artifacts import artifact_info
    from daw.commons.moderation import Visibility
    vis = vis or Visibility.of(view)
    row = view.library.one("SELECT output_blob FROM artifact WHERE id=?", (artifact,))
    if not row:
        return {"artifact": artifact, "replicated": False, "confirmations": [], "attempts": [],
                "reason": "not in the shared library: only published artifacts carry a replication badge"}
    derivation = artifact_info(view.library, artifact)["manifest"].get("derivation") or {}
    inputs = [item.get("blob") for item in derivation.get("inputs") or []]
    system = _system_id(view)
    names = {r["id"]: r["name"] for r in view.rows("SELECT id,name FROM agent")}
    confirmations, makers = [], None
    for event in view.rows("SELECT body FROM event WHERE kind='published' AND json_extract(body,'$.author')=? "
                           "ORDER BY seq", (system,)) if system else []:
        body = json.loads(event["body"])
        record = (body.get("evidence") or {}).get("replication") or {}
        if record.get("original") != artifact or "output_sha256" not in record:
            continue
        post = body["post"]
        if vis.withheld(post):
            confirmations.append({"post": post, "hidden": True, "reason": vis.reason(post), "replicated": False})
            continue
        agent, run, receipts = record.get("agent"), record.get("run"), record.get("receipts") or []
        if makers is None:  # read every participant's catalog only when there is a confirmation to check
            makers = sorted(p for p, made in producers(view, [artifact]).items() if artifact in made)
        criteria = {
            "different_participant": {"ok": bool(agent) and agent not in makers, "participant": agent,
                                      "participant_name": names.get(agent), "producers": makers,
                                      "route": f"/agent/{agent}"},
            "captured_execution": {"ok": bool(receipts) and dispatch_sandboxed(view.root, run)
                                   and all((r.get("stream") or {}).get("line") for r in receipts),
                                   "run": run, "sandboxed": dispatch_sandboxed(view.root, run),
                                   "receipts": [{"receipt_blob": r.get("receipt_blob"), "event": r.get("event"),
                                                 "helper": (r.get("stream") or {}).get("helper"),
                                                 "line": (r.get("stream") or {}).get("line")} for r in receipts],
                                   "route": f"/run/{run}"},
            "matching_inputs": {"ok": bool(receipts) and all(r.get("inputs") == inputs for r in receipts),
                                "inputs": inputs, "receipt_inputs": [r.get("inputs") for r in receipts],
                                "route": f"/artifact/{artifact}"},
            "identical_bytes": {"ok": record.get("output_sha256") == row["output_blob"],
                                "sha256": row["output_blob"], "replica_sha256": record.get("output_sha256"),
                                "replicas": record.get("registered") or [], "route": f"/post/{post}"}}
        confirmations.append({"post": post, "request": record.get("request"), "run": run, "agent": agent,
                              "criteria": criteria, "replicated": all(c["ok"] for c in criteria.values())})
    attempts = []
    for event in view.rows("SELECT seq,body,created FROM event WHERE kind='replication_checked' ORDER BY seq"):
        body = json.loads(event["body"])
        for result in body.get("results") or []:
            if result.get("original") == artifact:
                attempts.append({"request": body.get("request"), "run": body.get("run"), "agent": body.get("agent"),
                                 "outcome": result.get("outcome"), "post": result.get("post"),
                                 "created": event["created"], "route": f"/run/{body.get('run')}"})
    replicated = any(c["replicated"] for c in confirmations)
    return {"artifact": artifact, "replicated": replicated, "confirmations": confirmations, "attempts": attempts,
            "meaning": "Replicated: a different participant's captured execution of the saved derivation on its "
                       "recorded inputs wrote identical bytes. It confirms this derivation's output, not scientific "
                       "applicability."}
