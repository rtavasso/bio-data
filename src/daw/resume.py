"""`bio work resume Q`: one bounded record of where a question stands, for the start of a turn or the
first action after a compaction.

The PMP22 cohort re-oriented 129 times (57 compactions, 72 resumed deliveries). Its first eight calls after
each one took 161 minutes in all: inbox and show, `--help` crawls, re-reading outputs it had already read,
re-viewing skills. All of that is already on disk; this command reads it once and prints it in about 4 KB.
It changes nothing and judges nothing: status, the notebook's section heads and tail, registered outputs,
the latest execution receipts, inherited scripts with their first line, open items, and the command crib.
"""
import re
from pathlib import Path

from daw.util import DawError, read_json
from daw.work import question_record

MAX_TAIL_LINES = 12
MAX_SCRIPTS = 25
MAX_RECEIPTS = 6
MAX_ARTIFACTS = 25

# The verbs the cohort looked up most (`--help` 238 times: register 39, publish 28, artifact use 24, sync 23, object add 19).
COMMANDS = [
    "bio community overview                              # board: requests to you, acts on your work, your items, budget",
    "bio work resume Q                                   # workspace: this record",
    "bio community search --text '...' [--family artifact|work|claim]",
    "bio community show POST | bio community fetch POST --question Q",
    "./bin/python .agents/skills/bio-research/scripts/peek.py PATH [--grep RE]   # inspect a file, bounded",
    "./bin/python .agents/skills/bio-research/scripts/run_analysis.py --receipt outputs/NAME-execution-r001.json "
    "--output outputs/NAME.tsv -- ./bin/python scripts/NAME.py",
    "bio object add PATH   -> blob; bio register outputs/NAME.tsv --question Q --input BLOB|asset_|artifact_ "
    "--code scripts/NAME.py --output-role measurement-table|contrast-table|eligibility|source-locator|figure --title ...",
    "./bin/python .agents/skills/bio-research/scripts/records.py eligibility|locus --question Q --add k=v ... [--register]",
    "bio community publish TITLE --body FILE --question Q --artifact ARTIFACT --claims claims.json [--publish-cited]",
    "bio community verify POST --body FILE --numbers",
    "bio community answer REQUEST --body FILE   # a question addressed to you; closes it",
    "bio community reply THREAD --body FILE     # a comment or dispute at an anchor on your work",
    "bio community frontier --mine --limit 50 --offset 0 | bio work frontier Q --kind next_step --text '...'",
    "bio work gap Q --need ... --failed ... --source-or-format ...  | bio work frontier Q --kind ... --text ...",
    "bio work sync Q --summary '...'",
]


def _first_line(path):
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                text = line.strip()
                if not text or text.startswith("#!"):
                    continue
                return re.sub(r'^("""|\'\'\'|#)\s*', "", text).strip("\"' ")[:100]
    except OSError:
        return ""
    return ""


def _receipt(path):
    try:
        value = read_json(path)
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or "exit_code" not in value or "producer" not in value:
        return None
    return {"receipt": path.name, "producer": Path(str(value.get("producer"))).name, "exit_code": value.get("exit_code"),
            "complete": value.get("complete"), "finished": value.get("finished"),
            "outputs": [Path(o.get("path", "")).name for o in value.get("outputs", []) if isinstance(o, dict)][:6]}


def notebook_outline(text):
    lines = text.splitlines()
    heads = [line.strip()[:80] for line in lines if line.startswith("#")][:20]
    tail = [line[:160] for line in lines[-MAX_TAIL_LINES:]]
    return {"lines": len(lines), "bytes": len(text.encode()), "headings": heads, "tail": tail}


def resume_work(ws, qid, *, inbox=None):
    """The record described in the module docstring. `inbox` is an optional callable returning pending
    requests for the current agent (the CLI supplies it when BIO_COMMUNITY and BIO_AGENT are set)."""
    question, path = question_record(ws, qid)
    current = ws.one("SELECT body_blob FROM work_snapshot WHERE id=?", (question["current_work"],))
    snapshot = read_json(ws.blob_path(current["body_blob"])) if current else {}
    notebook = path / "LABBOOK.md"
    outline = notebook_outline(notebook.read_text(errors="replace")) if notebook.is_file() else None

    artifacts = []
    for row in ws.rows("SELECT qa.artifact_id AS id, qa.relationship, a.output_role, a.manifest_blob FROM question_artifact qa "
                       "JOIN artifact a ON a.id=qa.artifact_id WHERE qa.question_id=? ORDER BY a.created, qa.artifact_id", (qid,)):
        try:
            manifest = read_json(ws.blob_path(row["manifest_blob"]))
        except (DawError, OSError, ValueError):
            manifest = {}
        artifacts.append({"id": row["id"], "relationship": row["relationship"], "output_role": row["output_role"],
                          "title": (manifest.get("title") or "")[:80], "name": (manifest.get("output") or {}).get("name")})

    outputs = path / "outputs"
    receipts = []
    if outputs.is_dir():
        candidates = sorted((p for p in outputs.rglob("*.json") if p.is_file() and not p.is_symlink()
                             and p.stat().st_size < 1_000_000), key=lambda p: p.stat().st_mtime, reverse=True)
        for candidate in candidates[:200]:
            record = _receipt(candidate)
            if record:
                receipts.append(record)
            if len(receipts) >= MAX_RECEIPTS:
                break
    scripts_dir = path / "scripts"
    scripts = []
    if scripts_dir.is_dir() and not scripts_dir.is_symlink():
        ran = {r["producer"] for r in receipts}
        for script in sorted(p for p in scripts_dir.rglob("*") if p.is_file() and p.suffix in {".py", ".R", ".sh", ".sql"}):
            scripts.append({"path": str(script.relative_to(path)), "purpose": _first_line(script),
                            "has_recent_receipt": script.name in ran})
    output_files = sorted(p.name for p in outputs.iterdir() if p.is_file()) if outputs.is_dir() else []

    kinds = {}
    for row in ws.rows("SELECT kind, count(*) AS n FROM work_event WHERE question_id=? GROUP BY kind", (qid,)):
        kinds[row["kind"]] = row["n"]
    open_items = None
    try:
        from daw.commons.frontier import workspace_items
        items = workspace_items(ws, qid)
        open_items = [{"event": i["event"], "kind": i["kind"], "status": i["status"], "text": i["text"][:120]}
                      for i in items if i.get("status") in ("open", "candidate_evidence")][:15]
    except Exception:  # noqa: BLE001 - the frontier index is optional for this record
        open_items = None

    pending = None
    if inbox is not None:
        try:
            pending = [{"request": r["id"], "post": r["post"], "state": r["state"]} for r in inbox()][:10]
        except Exception as error:  # noqa: BLE001 - a board that is unreachable is reported, never fatal here
            pending = {"unavailable": type(error).__name__}

    return {"question": qid, "title": question["title"], "status": question["status"], "path": str(path),
            "summary": (snapshot.get("summary") or "")[:600],
            "notebook": outline,
            "artifacts": artifacts[:MAX_ARTIFACTS], "artifacts_total": len(artifacts),
            "latest_receipts": receipts,
            "scripts": scripts[:MAX_SCRIPTS], "scripts_total": len(scripts),
            "output_files": output_files[:40], "output_files_total": len(output_files),
            "events": kinds, "open_items": open_items, "pending_requests_for_you": pending,
            "commands": COMMANDS,
            "note": "Read-only. Re-read LABBOOK.md only to edit it; re-read an output only to use a value from it. "
                    "Run inherited scripts before writing new ones (fork rewrites in the cohort: 11 same-name scripts)."}
