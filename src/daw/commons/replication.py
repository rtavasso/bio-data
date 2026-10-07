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
  output blob. Otherwise the outcome is `no_execution_receipt` and nothing is confirmed. Receipts are read
  from the agent's workspace through `Archive` (read-only); the gate is structural, not a scientific verdict.
- `SYSTEM_PARTICIPANT`: confirmations and mismatch posts and marks are platform records authored by the
  `replication` system participant, citing the agent's receipt; agents sign only what they wrote.
"""
import json
from pathlib import Path

from daw.commons.archive import Archive
from daw.util import DawError

EXECUTION_EVENT = "replication_execution"
SYSTEM_PARTICIPANT = "replication"
RECEIPT_FIELDS = ("code_sha256", "producer", "exit_code", "started", "finished")


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

def check_receipt(ws, receipt_blob, code_blobs, output_blob):
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
    producer = str(receipt.get("producer") or "")
    summary = {"receipt_blob": receipt_blob, **{k: receipt.get(k) for k in RECEIPT_FIELDS},
               # Relative to the agent's workspace: host paths stay out of board records.
               "producer": producer[producer.index("questions/"):] if "questions/" in producer else Path(producer).name,
               "outputs": [{"sha256": o.get("sha256"), "written": o.get("written")} for o in receipt["outputs"]
                           if isinstance(o, dict)]}
    return summary, problems


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


def receipt_for(ws, events, code_blobs, output_blob):
    """(the first valid receipt for these bytes, problems of every candidate); candidates are execution events."""
    problems = []
    for event in events:
        summary, issues = check_receipt(ws, event["payload"]["receipt_blob"], code_blobs, output_blob)
        if summary and not issues:
            return {**summary, "event": event["id"], "question": event["question_id"]}, []
        problems.append({"event": event["id"], "receipt_blob": event["payload"]["receipt_blob"], "problems": issues})
    return None, problems or [{"problems": ["no_replication_execution_recorded"]}]


def reverify(board, agent, receipt, code_blobs, output_blob):
    """Re-read a receipt recorded in a task outcome from the agent's workspace (read-only); True when it still holds."""
    if not isinstance(receipt, dict) or not receipt.get("receipt_blob"):
        return False
    with Archive(board.root) as view:
        ws = view.workspace(agent)
        if ws is None:
            return False
        summary, problems = check_receipt(ws, receipt["receipt_blob"], code_blobs, output_blob)
    return bool(summary) and not problems


def receipt_line(receipt):
    return (f"run_analysis receipt `{receipt['receipt_blob']}` (workspace event {receipt.get('event')}): producer "
            f"code sha256 `{receipt['code_sha256']}`, exit code {receipt['exit_code']}, "
            f"started {receipt.get('started')}, finished {receipt.get('finished')}")
