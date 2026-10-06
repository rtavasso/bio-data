"""Ordinary question folders, versioned notebooks and recorded research events."""
import os
import uuid

from daw.search import index_document
from daw.util import DawError, canonical, now, read_json


def question_record(ws, qid):
    if (ws.root / "questions").is_symlink():
        raise DawError("unsafe_question_path")
    row = ws.one("SELECT * FROM question WHERE id=?", (qid,))
    if not row:
        raise DawError("unknown_question", qid)
    path = ws.root / row["path"]
    if path.is_symlink() or not path.resolve().is_relative_to((ws.root / "questions").resolve()):
        raise DawError("unsafe_question_path")
    return row, path


def record_event(ws, qid, kind, payload):
    _, path = question_record(ws, qid)
    if not kind or len(kind) > 100:
        raise DawError("invalid_event_kind")
    if kind == "retrieval_gap":
        from daw.gaps import validate_gap
        payload = validate_gap(payload, qid)
        if "evidence_blob" in payload:
            from daw.profiles import verify_object
            verify_object(ws, payload["evidence_blob"])
    if kind == "retrieval_gap_withdrawal":
        from daw.gaps import validate_withdrawal
        payload = validate_withdrawal(ws, payload, qid)
    body = ws.put_json(payload)
    event = {"id": "event_" + uuid.uuid4().hex, "question": qid, "kind": kind, "body_blob": body, "created": now()}
    with ws.db:
        ws.db.execute("INSERT INTO work_event VALUES(?,?,?,?,?)", (event["id"], qid, kind, body, event["created"]))
    # JSONL is a presentation of committed events. Rebuildable from SQLite.
    journal = path / "events.jsonl"
    if journal.is_symlink():
        raise DawError("unsafe_question_path")
    with journal.open("ab") as stream:
        stream.write(canonical(event) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return event


def create_question(ws, title, prompt=None):
    if not title.strip():
        raise DawError("empty_question_title")
    if (ws.root / "questions").is_symlink():
        raise DawError("unsafe_question_path")
    qid = "q_" + uuid.uuid4().hex[:16]
    relative = "questions/" + qid
    path = ws.root / relative
    path.mkdir(parents=True)
    for part in ("scripts", "outputs"):
        (path / part).mkdir()
    (path / "QUESTION.md").write_text(f"# {title}\n\n{prompt or title}\n")
    (path / "LABBOOK.md").write_text(f"# Research notebook: {title}\n\n"
        "## Investigation\n\n## Data and prior work\n\n## Findings\n\n"
        "## Failed routes\n\n## Assumptions and limitations\n\n## Open questions\n")
    with ws.db:
        ws.db.execute("INSERT INTO question VALUES(?,?,?,?,?,?,NULL)", (qid, title, "open", relative, now(), now()))
    record_event(ws, qid, "question_created", {"title": title})
    snapshot = sync_work(ws, qid)
    return {"question": qid, "path": str(path), "snapshot": snapshot["snapshot"],
            "next": "Edit LABBOOK.md, write normal scripts, register reusable outputs; no scientific acceptance gate"}


def safe_work_files(path):
    selected = [path / "QUESTION.md", path / "LABBOOK.md"]
    scripts = path / "scripts"
    if scripts.is_symlink():
        raise DawError("unsafe_question_path")
    if scripts.exists():
        selected.extend(sorted(p for p in scripts.rglob("*") if p.is_file() or p.is_symlink()))
    for item in selected:
        if item.is_symlink() or not item.resolve().is_relative_to(path.resolve()) or not item.is_file():
            raise DawError("unsafe_question_file", str(item))
    return selected


def sync_work(ws, qid, *, summary=None, status=None):
    question, path = question_record(ws, qid)
    status = status or question["status"]
    if status not in {"open", "completed", "paused"}:
        raise DawError("invalid_question_status")
    files = {}
    for item in safe_work_files(path):
        if ws.budgets.asset_bytes and item.stat().st_size > ws.budgets.asset_bytes:
            raise DawError("over_budget", "research notebook/script snapshot")
        files[str(item.relative_to(path))] = ws.put_file(item, "work")
    notebook = (path / "LABBOOK.md").read_text()
    question_text = (path / "QUESTION.md").read_text()
    if summary is None and question["current_work"]:
        prior = ws.one("SELECT body_blob FROM work_snapshot WHERE id=?", (question["current_work"],))
        summary = read_json(ws.blob_path(prior["body_blob"])).get("summary", "")
    artifacts = ws.rows("SELECT artifact_id,relationship FROM question_artifact WHERE question_id=? ORDER BY artifact_id,relationship", (qid,))
    body = {"question": qid, "title": question["title"], "status": status, "summary": summary or "",
            "files": files, "artifacts": artifacts, "question_path": question["path"]}
    blob = ws.put_json(body)
    wid = "work_" + blob
    with ws.db:
        ws.db.execute("INSERT OR IGNORE INTO work_snapshot VALUES(?,?,?,?)", (wid, qid, blob, now()))
        ws.db.execute("UPDATE question SET status=?,updated=?,current_work=? WHERE id=?", (status, now(), wid, qid))
    index_document(ws, key="work:" + qid, family="work", subject=qid, record_id=wid,
                   title=question["title"], summary=summary or "Notebook indexed; no summary supplied",
                   body_blob=blob, detail=question_text + "\n" + notebook, level=3)
    if question["current_work"] != wid:
        record_event(ws, qid, "work_snapshot", {"snapshot": wid, "status": status, "manifest": blob})
    return {"question": qid, "snapshot": wid, "blob": blob, "files": files, "status": status,
            "reused": question["current_work"] == wid}


def show_work(ws, qid, *, notebook=False, events=0):
    question, path = question_record(ws, qid)
    current = ws.one("SELECT body_blob FROM work_snapshot WHERE id=?", (question["current_work"],))
    result = {**question, "path": str(path), "snapshot": read_json(ws.blob_path(current["body_blob"])) if current else None}
    if notebook:
        safe_work_files(path)
        result["notebook"] = (path / "LABBOOK.md").read_text()
    if events:
        if not 1 <= events <= 100:
            raise DawError("invalid_event_limit")
        result["events"] = ws.rows("SELECT * FROM work_event WHERE question_id=? ORDER BY created DESC,id DESC LIMIT ?", (qid, events))
    return result


def rebuild_event_log(ws, qid):
    _, path = question_record(ws, qid)
    events = ws.rows("SELECT id,question_id AS question,kind,body_blob,created FROM work_event WHERE question_id=? ORDER BY created,id", (qid,))
    journal = path / "events.jsonl"
    if journal.is_symlink():
        raise DawError("unsafe_question_path")
    journal.write_bytes(b"".join(canonical(e) + b"\n" for e in events))
    return {"question": qid, "events": len(events)}
