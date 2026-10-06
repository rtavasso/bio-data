"""Question pages (M4.3): notebooks, outputs, hypothesis networks, coverage, gaps and the event scrubber.

Everything is read from a participant's workspace catalog with mode=ro. Notebook
text comes from immutable work-snapshot blobs, never from the mutable question
folder. Question-local hypothesis networks (`mechanisms*.json`) and evidence
coverage tables (`evidence-coverage*.tsv`) are agent-authored research artifacts:
they are parsed defensively and returned as given, never merged into any platform
biology. Their origin is always stated: a snapshot file, a registered artifact, a
blob whose hash the notebook cites (`bio object add`), or the mutable working copy
in `outputs/` (labelled as such; it is not a record).
"""
import csv
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from daw.gaps import report_gaps
from daw.profiles import verify_object
from daw.util import DawError

MAX_TEXT = 2 * 2**20
MAX_RESEARCH_FILE = 4 * 2**20
NETWORK = re.compile(r"(^|/)mechanisms(\.[A-Za-z0-9_-]+)?\.json$")
COVERAGE = re.compile(r"(^|/)evidence-coverage(\.[A-Za-z0-9_-]+)?\.tsv$")
SHA = re.compile(r"\b[0-9a-f]{64}\b")
IMAGES = {".png": ("image/png", b"\x89PNG\r\n\x1a\n"), ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
          ".jpeg": ("image/jpeg", b"\xff\xd8\xff"), ".svg": ("image/svg+xml", None)}
SUMMARY_KEYS = 12


def _workspace(view, agent):
    participant = view.participant(agent)
    ws = view.workspace(participant["id"])
    if ws is None:
        raise DawError("unknown_question", f"{participant['name']} has no research workspace")
    return participant, ws


def _question(ws, qid):
    row = ws.one("SELECT * FROM question WHERE id=?", (qid,))
    if not row:
        raise DawError("unknown_question", qid)
    return row


def _counts(ws):
    """Per-question counts in a few grouped queries (cheap for hundreds of questions)."""
    counts = {}

    def bump(qid, key, n):
        counts.setdefault(qid, {"events": 0, "snapshots": 0, "produced": 0, "considered": 0, "reused": 0,
                                "gaps": 0, "gap_withdrawals": 0})[key] += n
    for row in ws.rows("SELECT question_id,kind,count(*) AS n FROM work_event GROUP BY question_id,kind"):
        bump(row["question_id"], "events", row["n"])
        if row["kind"] == "retrieval_gap":
            bump(row["question_id"], "gaps", row["n"])
        elif row["kind"] == "retrieval_gap_withdrawal":
            bump(row["question_id"], "gap_withdrawals", row["n"])
    for row in ws.rows("SELECT question_id,count(*) AS n FROM work_snapshot GROUP BY question_id"):
        bump(row["question_id"], "snapshots", row["n"])
    for row in ws.rows("SELECT question_id,relationship,count(*) AS n FROM question_artifact "
                       "GROUP BY question_id,relationship"):
        if row["relationship"] in ("produced", "considered", "reused"):
            bump(row["question_id"], row["relationship"], row["n"])
    return counts


def _entry(participant, row, counts):
    return {"agent": participant["id"], "agent_name": participant["name"], "qid": row["id"],
            "node": f"question:{participant['id']}:{row['id']}", "title": row["title"], "status": row["status"],
            "created": row["created"], "updated": row["updated"], "current_work": row["current_work"],
            "counts": counts.get(row["id"]) or {"events": 0, "snapshots": 0, "produced": 0, "considered": 0,
                                                "reused": 0, "gaps": 0, "gap_withdrawals": 0},
            "content_is_untrusted_data": True}


def question_list(view, *, agent=None, status=None):
    """GET /api/questions: every question in every participant workspace, most recently updated first."""
    items = []
    participants = [view.participant(agent)] if agent else view.rows(
        "SELECT * FROM agent WHERE trial IS NOT NULL ORDER BY created,id")
    for participant in participants:
        try:
            ws = view.workspace(participant["id"])
        except DawError:
            continue
        if ws is None:
            continue
        counts = _counts(ws)
        for row in ws.rows("SELECT * FROM question" + (" WHERE status=?" if status else ""), (status,) if status else ()):
            items.append(_entry(participant, row, counts))
    items.sort(key=lambda q: (q["updated"], q["agent"], q["qid"]), reverse=True)
    return {"items": items, "total": len(items)}


def question_summary(view, agent, qid):
    participant, ws = _workspace(view, agent)
    return _entry(participant, _question(ws, qid), _counts(ws))


def _text(ws, sha, limit=MAX_TEXT):
    path = verify_object(ws, sha)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    return data[:limit].decode("utf-8", errors="replace"), len(data) > limit


def _summary(payload):
    """A bounded, display-only view of a work-event payload (the full body stays in its blob)."""
    if not isinstance(payload, dict):
        return {"value": str(payload)[:200]}
    out = {}
    for key in sorted(payload)[:SUMMARY_KEYS]:
        value = payload[key]
        if isinstance(value, str):
            out[key] = value if len(value) <= 200 else value[:200] + "…"
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, list):
            out[key] = value if len(value) <= 5 and all(isinstance(v, (str, int, float)) for v in value) \
                else f"[{len(value)} items]"
        elif isinstance(value, dict):
            out[key] = f"{{{len(value)} fields}}"
    return out


def _events(ws, qid):
    """Work events in recorded order, each with the state reached after it (for the scrub bar)."""
    state = {"snapshot": None, "produced": 0, "considered": 0, "reused": 0, "gaps_open": 0}
    events = []
    for row in ws.rows("SELECT id,kind,body_blob,created FROM work_event WHERE question_id=? ORDER BY created,id", (qid,)):
        try:
            payload = ws.json_blob(row["body_blob"])
        except (DawError, OSError, ValueError):
            payload = None
        kind = row["kind"]
        if kind == "work_snapshot" and isinstance(payload, dict):
            state["snapshot"] = payload.get("snapshot")
        elif kind.startswith("artifact_") and kind[9:] in ("produced", "considered", "reused"):
            state[kind[9:]] += 1
        elif kind == "retrieval_gap":
            state["gaps_open"] += 1
        elif kind == "retrieval_gap_withdrawal":
            state["gaps_open"] = max(0, state["gaps_open"] - 1)
        events.append({"id": row["id"], "kind": kind, "created": row["created"], "body_blob": row["body_blob"],
                       "summary": _summary(payload) if payload is not None else {"unreadable": True},
                       "state": dict(state)})
    return events


def _revisions(ws, qid):
    revisions = []
    for row in ws.rows("SELECT id,body_blob,created FROM work_snapshot WHERE question_id=? ORDER BY created,id", (qid,)):
        try:
            body = ws.json_blob(row["body_blob"])
        except (DawError, OSError, ValueError):
            body = {}
        revisions.append({"id": row["id"], "created": row["created"], "body_blob": row["body_blob"],
                          "status": body.get("status"), "summary": (body.get("summary") or "")[:300],
                          "files": body.get("files") if isinstance(body.get("files"), dict) else {}})
    return revisions


def _outputs(ws, agent, qid):
    from daw.artifacts import reuse_links
    backed = {(r["artifact"], r["relationship"]): r for r in reuse_links(ws) if r["question"] == qid}
    outputs = {}
    for link in ws.rows("SELECT qa.artifact_id,qa.relationship,qa.event_id,e.created FROM question_artifact qa "
                        "JOIN work_event e ON e.id=qa.event_id WHERE qa.question_id=? ORDER BY e.created,qa.artifact_id",
                        (qid,)):
        aid = link["artifact_id"]
        if aid not in outputs:
            row = ws.one("SELECT * FROM artifact WHERE id=?", (aid,)) or {}
            try:
                manifest = ws.json_blob(row["manifest_blob"]) if row else {}
            except (DawError, OSError, ValueError):
                manifest = {}
            output = manifest.get("output") if isinstance(manifest.get("output"), dict) else {}
            name = output.get("name") or ""
            role = row.get("output_role") or ""
            outputs[aid] = {"artifact": aid, "present": bool(row), "title": manifest.get("title"),
                            "summary": (manifest.get("summary") or "")[:400], "output_role": role, "output_name": name,
                            "output_blob": row.get("output_blob"), "bytes": output.get("bytes"),
                            "created": row.get("created"), "limitations": manifest.get("limitations") or [],
                            "figure": Path(name).suffix.lower() in IMAGES or role.split("-")[0] == "figure",
                            "blob_url": f"/api/blobs/{agent}/{row['output_blob']}?name={name}" if row else None,
                            "relationships": []}
        relation = {"relationship": link["relationship"], "event": link["event_id"], "created": link["created"]}
        if link["relationship"] == "reused":
            entry = backed.get((aid, "reused"), {})
            relation.update(backed=entry.get("backed"), reason=entry.get("reason"), input_to=entry.get("input_to"))
        outputs[aid]["relationships"].append(relation)
    return list(outputs.values())


def _parse_network(data):
    """Render a question-local mechanism map as given. Malformed parts are reported, not repaired."""
    empty = {"revision": None, "scope": None, "nodes": [], "edges": [], "frontier": [], "changes": [], "issues": []}
    try:
        value = json.loads(data)
    except ValueError as e:
        return {**empty, "error": f"invalid JSON: {e}"}
    if not isinstance(value, dict):
        return {**empty, "error": "expected a JSON object with nodes and edges"}
    nodes = [n for n in value.get("nodes") or [] if isinstance(n, dict) and isinstance(n.get("id"), (str, int))]
    ids = {str(n["id"]) for n in nodes}
    edges = []
    for edge in value.get("edges") or []:
        if isinstance(edge, dict) and isinstance(edge.get("source"), (str, int)) and isinstance(edge.get("target"), (str, int)):
            edges.append({**edge, "dangling": str(edge["source"]) not in ids or str(edge["target"]) not in ids})
    frontier = [f for f in value.get("frontier") or [] if isinstance(f, dict)]
    changes = value.get("changes") if isinstance(value.get("changes"), list) else []
    revision = value.get("revision") if isinstance(value.get("revision"), int) else None
    issues = []
    if not isinstance(value.get("nodes"), list):
        issues.append("nodes missing or not a list")
    if not isinstance(value.get("edges"), list):
        issues.append("edges missing or not a list")
    skipped = (len(value.get("nodes") or []) - len(nodes) if isinstance(value.get("nodes"), list) else 0)
    if skipped:
        issues.append(f"{skipped} node entries without an id were skipped")
    return {"revision": revision, "scope": value.get("scope") if isinstance(value.get("scope"), dict) else None,
            "nodes": nodes, "edges": edges, "frontier": frontier, "changes": changes, "issues": issues}


def _parse_coverage(data):
    """TSV kept as text. A short row's absent cells are null (missing); present empty cells are "" (blank)."""
    text = data.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t"))
    if not rows:
        return {"columns": [], "rows": [], "issues": ["empty file"]}
    columns, body = rows[0], rows[1:]
    out, issues = [], []
    for number, row in enumerate(body, 2):
        if not any(cell.strip() for cell in row):
            continue
        cells = [row[i] if i < len(row) else None for i in range(len(columns))]
        entry = {"line": number, "cells": cells}
        if len(row) > len(columns):
            entry["extra"] = row[len(columns):]
            issues.append(f"line {number}: {len(row) - len(columns)} cells beyond the header")
        if len(row) < len(columns):
            issues.append(f"line {number}: {len(columns) - len(row)} cells missing")
        out.append(entry)
    return {"columns": columns, "rows": out, "issues": issues}


def _working_copy(question_path, pattern):
    """Mutable files in the question folder: shown, labelled, never treated as records."""
    found = []
    for folder in (question_path / "outputs", question_path):
        if not folder.is_dir() or folder.is_symlink():
            continue
        for path in sorted(folder.iterdir()):
            if (not path.is_file() or path.is_symlink() or not pattern.search(path.name)
                    or not path.resolve().is_relative_to(question_path.resolve())
                    or path.stat().st_size > MAX_RESEARCH_FILE):
                continue
            found.append((str(path.relative_to(question_path)), path.read_bytes(),
                          datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()))
    return found


def _research_files(ws, question_path, revisions, outputs):
    """Network and coverage files by origin, deduplicated by content hash."""
    import hashlib
    candidates = {}

    def add(name, origin, loader):
        kind = "network" if NETWORK.search(name) else "coverage" if COVERAGE.search(name) else None
        if kind is None:
            return
        try:
            data = loader()
        except (DawError, OSError):
            return
        if data is None or len(data) > MAX_RESEARCH_FILE:
            return
        sha = hashlib.sha256(data).hexdigest()
        entry = candidates.setdefault(sha, {"kind": kind, "sha256": sha, "name": name, "data": data, "origins": []})
        if origin not in entry["origins"]:
            entry["origins"].append(origin)

    def blob_loader(sha):
        return lambda: verify_object(ws, sha).read_bytes()
    for revision in revisions:
        for path, sha in sorted(revision["files"].items()):
            add(path, {"kind": "snapshot", "id": revision["id"], "path": path, "created": revision["created"]},
                blob_loader(sha))
    for output in outputs:
        if output["present"] and output["output_name"]:
            add(output["output_name"], {"kind": "artifact", "id": output["artifact"], "created": output["created"]},
                blob_loader(output["output_blob"]))
    cited = {}
    for revision in revisions:
        sha = revision["files"].get("LABBOOK.md")
        if not sha:
            continue
        try:
            text, _ = _text(ws, sha)
        except (DawError, OSError):
            continue
        for found in SHA.findall(text):
            cited.setdefault(found, revision)
    for sha, revision in cited.items():
        row = ws.one("SELECT size,classification FROM blob WHERE sha256=?", (sha,))
        if not row or row["size"] > MAX_RESEARCH_FILE:
            continue
        data = verify_object(ws, sha).read_bytes()
        try:
            value = json.loads(data)
            name = "mechanisms.json" if isinstance(value, dict) and isinstance(value.get("nodes"), list) else None
        except ValueError:
            first = data.split(b"\n", 1)[0].decode("utf-8", errors="replace")
            name = "evidence-coverage.tsv" if "\t" in first and "inspection_status" in first else None
        if name:
            add(name, {"kind": "notebook_hash", "id": revision["id"], "classification": row["classification"],
                       "created": revision["created"]}, lambda data=data: data)
    for name, data, modified in _working_copy(question_path, NETWORK):
        add(name, {"kind": "working_copy", "path": name, "modified": modified,
                   "note": "mutable file in the question folder; not an immutable record"}, lambda data=data: data)
    for name, data, modified in _working_copy(question_path, COVERAGE):
        add(name, {"kind": "working_copy", "path": name, "modified": modified,
                   "note": "mutable file in the question folder; not an immutable record"}, lambda data=data: data)
    networks, coverage = [], []
    for entry in candidates.values():
        data = entry.pop("data")
        entry["preserved"] = bool(ws.one("SELECT sha256 FROM blob WHERE sha256=?", (entry["sha256"],)))
        entry["records"] = [o for o in entry["origins"] if o["kind"] != "working_copy"]
        entry["created"] = min((o.get("created") or o.get("modified") or "") for o in entry["origins"])
        if entry["kind"] == "network":
            networks.append({**entry, **_parse_network(data)})
        else:
            coverage.append({**entry, **_parse_coverage(data)})
    networks.sort(key=lambda n: (n["revision"] is None, n["revision"] or 0, n["created"], n["sha256"]))
    coverage.sort(key=lambda c: (c["created"], c["sha256"]))
    return networks, coverage


def question_page(view, agent, qid, *, snapshot=None):
    """GET /api/questions/{agent}/{qid}: the question as recorded, at the current or a chosen snapshot."""
    from daw.commons.evidence_map import question_subgraph
    from daw.commons.participants import describe
    from daw.work import question_record
    participant, ws = _workspace(view, agent)
    row = _question(ws, qid)
    _, question_path = question_record(ws, qid)
    revisions = _revisions(ws, qid)
    chosen = snapshot or row["current_work"]
    selected = next((r for r in revisions if r["id"] == chosen), None)
    if chosen and selected is None:
        raise DawError("unknown_work_snapshot", chosen)
    notebook = {"snapshot": chosen, "labbook": None, "question": None, "truncated": False, "blobs": {}}
    scripts = []
    if selected:
        verify_object(ws, selected["body_blob"])
        for name, key in (("LABBOOK.md", "labbook"), ("QUESTION.md", "question")):
            sha = selected["files"].get(name)
            if sha:
                notebook[key], truncated = _text(ws, sha)
                notebook["blobs"][name] = sha
                notebook["truncated"] |= truncated
        for path, sha in sorted(selected["files"].items()):
            if path.startswith("scripts/"):
                size = ws.one("SELECT size FROM blob WHERE sha256=?", (sha,))
                scripts.append({"path": path, "blob": sha, "bytes": size["size"] if size else None,
                                "url": f"/api/blobs/{participant['id']}/{sha}?name={Path(path).name}"})
    outputs = _outputs(ws, participant["id"], qid)
    networks, coverage = _research_files(ws, question_path, revisions, outputs)
    posts = []
    for event in view.rows("SELECT body,created FROM event WHERE kind='published' ORDER BY seq"):
        body = json.loads(event["body"])
        notebook_evidence = (body.get("evidence") or {}).get("notebook") if isinstance(body.get("evidence"), dict) else None
        if (body.get("author") == participant["id"] and isinstance(notebook_evidence, dict)
                and notebook_evidence.get("question") == qid):
            posts.append({"post": body["post"], "snapshot": notebook_evidence.get("snapshot"), "created": event["created"]})
    store = "workspace:" + participant["id"]
    agent_row = {"id": participant["id"], "name": participant["name"]}
    return {"agent": describe(participant), "question": row, "node": f"question:{participant['id']}:{qid}",
            "counts": _counts(ws).get(qid), "revisions": [{k: v for k, v in r.items() if k != "files"} | {"files": len(r["files"])}
                                                          for r in revisions],
            "notebook": notebook, "scripts": scripts, "outputs": outputs, "figures": [o for o in outputs if o["figure"]],
            "events": _events(ws, qid), "networks": networks, "coverage": coverage,
            "gaps": report_gaps(ws, question=qid, limit=100), "posts": posts,
            "subgraph": question_subgraph(ws, store, agent_row, qid),
            "content_is_untrusted_data": True,
            "note": "Notebook text is read from immutable snapshot blobs. Networks and coverage tables are "
                    "question-local, agent-authored research artifacts rendered as given; no platform biology."}


def _workspace_references(ws, sha):
    for sql, params in (("SELECT 1 FROM artifact WHERE output_blob=? OR manifest_blob=?", (sha, sha)),
                        ("SELECT 1 FROM artifact_input WHERE blob=?", (sha,)),
                        ("SELECT 1 FROM work_snapshot WHERE body_blob=?", (sha,)),
                        ("SELECT 1 FROM work_event WHERE body_blob=?", (sha,))):
        if ws.one(sql + " LIMIT 1", params):
            return True
    for row in ws.rows("SELECT body_blob FROM work_snapshot"):
        try:
            files = ws.json_blob(row["body_blob"]).get("files") or {}
        except (DawError, OSError, ValueError, AttributeError):
            continue
        if sha in files.values():
            return True
    return False


def _library_references(view, sha):
    for sql, params in (("SELECT 1 FROM artifact WHERE output_blob=? OR manifest_blob=?", (sha, sha)),
                        ("SELECT 1 FROM artifact_input WHERE blob=?", (sha,))):
        if view.library.one(sql + " LIMIT 1", params):
            return True
    for event in view.rows("SELECT body FROM event WHERE kind='published' ORDER BY seq"):
        evidence = json.loads(event["body"]).get("evidence")
        notebook = evidence.get("notebook") if isinstance(evidence, dict) else None
        if not isinstance(notebook, dict) or not isinstance(notebook.get("manifest_blob"), str):
            continue
        if notebook["manifest_blob"] == sha:
            return True
        try:
            if sha in (view.library.json_blob(notebook["manifest_blob"]).get("files") or {}).values():
                return True
        except (DawError, OSError, ValueError, AttributeError):
            continue
    return False


def blob_file(view, owner, sha, name=None):
    """Resolve GET /api/blobs/{owner}/{sha}: only blobs referenced by that store's records.

    Returns (path, media_type, filename, attachment). Media types are text/plain or a
    raster/SVG image whose name and leading bytes agree; never HTML. SVG is an attachment.
    """
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise DawError("invalid_blob_hash")
    if owner == "library":
        ws, referenced = view.library, _library_references(view, sha)
    else:
        _, ws = _workspace(view, owner)
        referenced = _workspace_references(ws, sha)
    if not referenced:
        raise DawError("unknown_blob", "not referenced by this store's records")
    path = verify_object(ws, sha)
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name or "").name)[:120] or sha
    media, attachment = "text/plain; charset=utf-8", False
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGES:
        kind, magic = IMAGES[suffix]
        with path.open("rb") as stream:
            head = stream.read(8)
        if magic is None or head.startswith(magic):
            media, attachment = kind, suffix == ".svg"
    return path, media, filename, attachment


# --- synthetic demo records -------------------------------------------------------------------------

def _png(width, height, pixel):
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes(c for x in range(width) for c in pixel(x, y)) for y in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def demo_extension(board, ctx):
    """Demo records for question pages: a revised mechanism map and coverage table preserved by hash in
    Dana's notebook (as `bio object add` would), and a figure artifact derived from her search receipt."""
    from daw.artifacts import register_artifact
    from daw.catalog import Workspace
    from daw.commons.demo import SYNTHETIC, notebook
    from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
    from daw.work import sync_work
    agent = board.agent(ctx["agents"]["dana"])
    qid = ctx["questions"]["dana"]
    root = board.trial(agent) / "workspace"
    folder = root / "questions" / qid / "outputs"
    initial = {"revision": 1, "scope": {"target": "demo marker", "endpoint": "per-sample counts",
                                        "context": "synthetic demo; no species", "assumptions": [SYNTHETIC]},
               "nodes": [{"id": "marker", "label": "Demo marker abundance", "kind": "abundance"},
                         {"id": "readout", "label": "Condition readout", "kind": "phenotype"}],
               "edges": [{"id": "e1", "source": "marker", "target": "readout", "mechanism": "unspecified",
                          "context": "synthetic", "status": "hypothesis", "evidence": []}],
               "frontier": [{"node": "marker", "question": "Does knockdown change the readout?", "priority": "high: "
                             "the only discriminating perturbation", "reason": "no dataset located", "status": "open"}],
               "changes": []}
    revised = {**initial, "revision": 2,
               "edges": initial["edges"] + [{"id": "e2", "source": "readout", "target": "marker", "mechanism": "feedback",
                                             "context": "synthetic", "status": "hypothesis", "evidence": []}],
               "changes": [{"reason": "Added a feedback alternative; no data distinguishes the directions yet.",
                            "evidence": [{"source": ctx["gap_event"], "locator": "retrieval_gap",
                                          "basis": "search found no knockdown series"}]}]}
    coverage = ("edge_ids\talternatives\tobservation\tfile_or_accession\tanalysis\tinspection_status\tsource_locator\t"
                "result_or_limitation\tnext_action\n"
                "e1;e2\tforward vs feedback\tcounts after marker knockdown\t\tcompare readout by knockdown\tunavailable\t\t"
                "No knockdown series located.\tRe-run the scoped search\n"
                "e1\tforward vs none\tbaseline marker counts\t\tcorrelate marker with readout\tsearched\n")
    ws = Workspace(root)
    try:
        with ws.writer():
            hashes = {}
            for name, data in (("mechanisms.initial.json", json.dumps(initial, indent=1).encode()),
                               ("mechanisms.json", json.dumps(revised, indent=1).encode()),
                               ("evidence-coverage.tsv", coverage.encode())):
                (folder / name).write_bytes(data)
                hashes[name] = ws.put_file(folder / name, "interpretation")
            source = ws.one("SELECT body_blob FROM work_event WHERE id=?", (ctx["gap_event"],))["body_blob"]
            figure = folder / "search-hits.png"
            figure.write_bytes(_png(96, 64, lambda x, y: (200, 60, 60) if 20 <= x < 36 and y > 52 else
                                    (60, 90, 160) if 56 <= x < 72 and y > 60 else (250, 249, 245)))
            code = ws.put_bytes(b"# synthetic figure code (never executed)\n")
            spec = ArtifactRegistration(title="Search hits per source (synthetic)", output_role="figure",
                                        summary="Bar chart of repository search hits. " + SYNTHETIC,
                                        derivation=Derivation(inputs=[ObjectInput(blob=source, role="search-receipt")],
                                                              code=[code], parameters={"plot": "bar"}, references=[],
                                                              environment={"demo": True}),
                                        limitations=[SYNTHETIC])
            artifact = register_artifact(ws, figure, spec, question=qid)
            (root / "questions" / qid / "LABBOOK.md").write_text(notebook(
                "Perturbation search", "- No eligible dataset found.\n"
                f"- Mechanism map r1 `{hashes['mechanisms.initial.json']}`, r2 `{hashes['mechanisms.json']}`; "
                f"coverage `{hashes['evidence-coverage.tsv']}`.\n- Figure {artifact['artifact']}.",
                "- Exact missing measurement: per-sample counts after marker knockdown."))
            sync_work(ws, qid)
    finally:
        ws.close()
    ctx["observatory_map"] = {"figure": artifact["artifact"], "network_blobs": [hashes["mechanisms.initial.json"],
                              hashes["mechanisms.json"]], "coverage_blob": hashes["evidence-coverage.tsv"]}
