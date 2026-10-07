"""Federation that resolves (spec v2 V7): a read-only index of imported snapshots' records, foreign pointers
that resolve to bytes, and the record of which snapshots this board's questions cite.

**The index.** `export.import_snapshot` stores a verified snapshot read-only under
`<commons>/federation/<snapshot_id>/`. `index_snapshot` (called by every import and fetch) and `reindex`
(operator: `bio commons federation reindex`) register the snapshot's claim and artifact identities in the
`federation_record` table, a projection rebuilt from the imported directories alone: each directory is
re-verified first (a tampered or partial copy is not indexed), then its `records.json` (written by every
export since V7; preprints too) is read. A snapshot exported before `records.json` existed indexes its
artifacts from `artifacts/<id>/manifest.json` and no claims. The rows are disposable; the event
`federation_indexed` records each change. Nothing from a foreign snapshot is ever executed or written
into this board's posts, claims or library.

**Pointers across commons.** A write-up cites a record of an imported snapshot as

    snapshot:<snapshot id>/claim_<32 hex>
    snapshot:<snapshot id>/artifact_<64 hex>[#locator]

in any pointer form (`[1.54](snapshot:…/artifact_…#row=B_vs_A;col=log2_ratio)`, `[snapshot:…/claim_…]`, or
bare). The checker resolves it through the index and runs the same value-in-record check against the
snapshot's stored bytes (verified against the snapshot's manifest hash); the citation itself carries the
snapshot id, which is the sha256 of the snapshot's `snapshot.json`. An unknown snapshot or record is
unresolved (refused in a write-up), never guessed.

**Citations.** `citations(view)` lists the posts on this board whose text contains a foreign pointer
(recorded citations only: what the author wrote), grouped by snapshot, with the question each post
published (its notebook) or else its thread. Hidden posts and withheld write-ups are not counted.

**Incoming citations (spec v3 V16).** The cited commons learns of a citation the way it learns of anything
foreign: by importing the citing commons' snapshot. Every export lists, in `records.json`, the foreign
records its visible posts name (`citations`, read from the post text at the source); the index keeps an
entry only when the citing post's exported page or source in the verified snapshot contains the pointer,
so nothing is inferred. `cited_by(view, record)` then lists the indexed citations of snapshots this board
exported itself (its `snapshot_exported` and `preprint_exported` events), for the claim and artifact pages
and the dashboard. A citation of a snapshot this board did not export is never attributed to it, even when
the record id also exists here.

**Attribution (spec v3 B9).** `import_and_index` takes the importing participant (permission `import`):
the import receipt names it, `federation_indexed` carries it as `actor`, and every import act records a
`snapshot_imported` event (listed on the participant's `/me`). `reindex` is attributed the same way.
"""
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from daw.util import DawError, canonical, digest, now

RECORDS = "records.json"
RECORDS_FORMAT = "colloquy.snapshot-records/1"
FOREIGN = re.compile(r"snapshot:([0-9a-f]{64})/((?:claim_[0-9a-f]{32})|(?:artifact_[0-9a-f]{64}))")
FOREIGN_POINTER = re.compile(r"^snapshot:([0-9a-f]{64})/(claim_[0-9a-f]{32}|artifact_[0-9a-f]{64})$")
FOREIGN_SHAPE = re.compile(r"^snapshot:[^\s]*$")
CLAIM_ID = re.compile(r"^claim_[0-9a-f]{32}$")
ARTIFACT_ID = re.compile(r"^artifact_[0-9a-f]{64}$")
POST_ID = re.compile(r"^post_[0-9a-f]{32}$")
SNAPSHOT_ID = re.compile(r"^[0-9a-f]{64}$")
READ_LIMIT = 32 * 1024 * 1024


def split(identity):
    """`snapshot:<id>/claim_…` -> (snapshot, record) or None."""
    match = FOREIGN_POINTER.match(identity or "")
    return (match.group(1), match.group(2)) if match else None


def kind_of(identity):
    parts = split(identity)
    if not parts:
        return None
    return "claim" if parts[1].startswith("claim_") else "artifact"


def pointer(snapshot, record):
    return f"snapshot:{snapshot}/{record}"


# ---------------------------------------------------------------------------- reading a snapshot directory

def _listed(manifest):
    return {e["path"]: e for e in manifest["files"] if isinstance(e, dict) and isinstance(e.get("path"), str)}


def _records_from_manifests(folder, listed):
    """Artifacts of a snapshot without records.json, from artifacts/<id>/manifest.json (no claims)."""
    artifacts = []
    for path in sorted(listed):
        parts = path.split("/")
        if len(parts) != 3 or parts[0] != "artifacts" or parts[2] != "manifest.json" or not ARTIFACT_ID.match(parts[1]):
            continue
        try:
            record = json.loads((folder / path).read_bytes())
        except ValueError:
            continue
        aid, output_blob = parts[1], record.get("output_blob")
        output = next((p for p, e in listed.items() if p.startswith(f"artifacts/{aid}/") and p != path
                       and e.get("sha256") == output_blob), None)
        manifest = record.get("manifest") or {}
        artifacts.append({"id": aid, "title": manifest.get("title"), "output_role": manifest.get("output_role"),
                          "manifest_path": path,
                          "output": {"path": output, "sha256": output_blob, "bytes": listed[output]["bytes"],
                                     "name": Path(output).name} if output else {"sha256": output_blob, "present": False}})
    return {"format": RECORDS_FORMAT, "posts": [], "claims": [], "artifacts": artifacts, "derived": "manifests"}


def snapshot_records(folder):
    """(snapshot id, records) of a verified snapshot directory. Raises DawError when it does not verify."""
    from daw.commons import export
    folder = Path(folder)
    snapshot, manifest = export.read_manifest(folder)
    export.verify_directory(folder, manifest)
    listed = _listed(manifest)
    if RECORDS in listed:
        try:
            records = json.loads((folder / RECORDS).read_bytes())
        except ValueError as error:
            raise DawError("invalid_snapshot_records", str(error)) from error
        if not isinstance(records, dict) or records.get("format") != RECORDS_FORMAT:
            raise DawError("invalid_snapshot_records", f"{RECORDS} must be {RECORDS_FORMAT}")
    else:
        records = _records_from_manifests(folder, listed)
    return snapshot, manifest, _validated(records, listed, folder)


def _backed(folder, listed, post, cited):
    """True when the citing post's exported page or source (files the verified snapshot lists) names `cited`."""
    for path in (f"posts/{post}.html", f"source/{post}.md"):
        entry = listed.get(path)
        if entry and entry.get("bytes", READ_LIMIT + 1) <= READ_LIMIT and cited.encode() in (Path(folder) / path).read_bytes():
            return True
    return False


def _validated(records, listed, folder=None):
    """Keep only well-formed entries whose paths are files the snapshot lists (foreign data is untrusted)."""
    def text(value, limit=20000):
        return value[:limit] if isinstance(value, str) else None

    claims, artifacts, posts = [], [], []
    for claim in records.get("claims") or []:
        if not isinstance(claim, dict) or not CLAIM_ID.match(str(claim.get("id"))):
            continue
        claims.append({"id": claim["id"], "post": claim.get("post") if POST_ID.match(str(claim.get("post"))) else None,
                       "ordinal": claim.get("ordinal") if isinstance(claim.get("ordinal"), int) else None,
                       "text": text(claim.get("text")) or "", "status": text(claim.get("status"), 40),
                       "scope": claim.get("scope") if isinstance(claim.get("scope"), dict) else {},
                       "pointers": [p for p in claim.get("pointers") or [] if isinstance(p, dict)][:100],
                       "withdrawn_by": claim.get("withdrawn_by") if POST_ID.match(str(claim.get("withdrawn_by"))) else None})
    for item in records.get("artifacts") or []:
        if not isinstance(item, dict) or not ARTIFACT_ID.match(str(item.get("id"))):
            continue
        output = item.get("output") if isinstance(item.get("output"), dict) else {}
        path = output.get("path") if output.get("path") in listed else None
        sha = listed[path]["sha256"] if path else (output.get("sha256") if re.match(r"^[0-9a-f]{64}$", str(output.get("sha256"))) else None)
        artifacts.append({"id": item["id"], "title": text(item.get("title"), 500), "output_role": text(item.get("output_role"), 200),
                          "derivation_key": text(item.get("derivation_key"), 200),
                          "manifest_path": item.get("manifest_path") if item.get("manifest_path") in listed else None,
                          "path": path, "sha256": sha, "bytes": listed[path]["bytes"] if path else None,
                          "name": Path(path).name if path else text(output.get("name"), 300), "present": bool(path)})
    for post in records.get("posts") or []:
        if isinstance(post, dict) and POST_ID.match(str(post.get("id"))):
            posts.append({"id": post["id"], "title": text(post.get("title"), 500), "withheld": bool(post.get("withheld")),
                          "author": text(post.get("author"), 200), "created": text(post.get("created"), 40)})
    visible = {p["id"] for p in posts if not p["withheld"]}
    citations, seen = [], set()
    for item in (records.get("citations") or []) if folder is not None else []:
        if not isinstance(item, dict) or item.get("post") not in visible or not SNAPSHOT_ID.match(str(item.get("snapshot"))) \
                or not (CLAIM_ID.match(str(item.get("record"))) or ARTIFACT_ID.match(str(item.get("record")))):
            continue
        cited = pointer(item["snapshot"], item["record"])
        if (item["post"], cited) in seen or not _backed(folder, listed, item["post"], cited):
            continue  # recorded at the source only: the citing post's own exported text must name the record
        seen.add((item["post"], cited))
        citations.append({"post": item["post"], "snapshot": item["snapshot"], "record": item["record"]})
    return {"claims": claims, "artifacts": artifacts, "posts": posts, "citations": citations,
            "derived": records.get("derived", RECORDS)}


# ---------------------------------------------------------------------------- the index (writes)

def ensure_table(board):
    """Create the index table on the first federation write (caller holds the board writer lock)."""
    from daw.commons.schema import FEDERATION_TABLES
    if not board.one("SELECT name FROM sqlite_master WHERE type='table' AND name='federation_record'"):
        board.db.executescript(FEDERATION_TABLES)


def _rows(snapshot, records, stamp):
    rows = []
    titles = {p["id"]: p["title"] for p in records["posts"]}
    for claim in records["claims"]:
        body = {k: claim[k] for k in ("text", "status", "scope", "pointers", "ordinal", "withdrawn_by")}
        body["post_title"] = titles.get(claim["post"])
        rows.append((snapshot, claim["id"], "claim", claim["post"], None, None, canonical(body).decode(), stamp))
    for item in records["artifacts"]:
        body = {k: item[k] for k in ("title", "output_role", "derivation_key", "manifest_path", "name", "bytes", "present")}
        rows.append((snapshot, item["id"], "artifact", None, item["path"], item["sha256"], canonical(body).decode(), stamp))
    posts = {p["id"]: p for p in records["posts"]}
    for item in records["citations"]:
        post = posts[item["post"]]
        body = {"cited_snapshot": item["snapshot"], "cited_record": item["record"],
                "cited_kind": "claim" if item["record"].startswith("claim_") else "artifact",
                "post_title": post["title"], "author": post["author"], "created": post["created"]}
        rows.append((snapshot, f"citation:{item['post']}:{pointer(item['snapshot'], item['record'])}", "citation",
                     item["post"], None, None, canonical(body).decode(), stamp))
    return rows


def _state_key(rows):
    return digest([list(r[:7]) for r in rows])


def index_snapshot(board, snapshot, *, source=None, actor=None):
    """Register one imported snapshot's claims, artifacts and citations (idempotent; one `federation_indexed`
    event, attributed to `actor`, a participant id the caller has checked, when the rows change). The snapshot
    directory is re-verified first."""
    folder = Path(board.root) / "federation" / snapshot
    if not re.match(r"^[0-9a-f]{64}$", snapshot or "") or not (folder / "snapshot.json").is_file():
        raise DawError("unknown_snapshot", str(snapshot)[:80])
    found, _, records = snapshot_records(folder)
    if found != snapshot:
        raise DawError("snapshot_id_mismatch", f"{snapshot} holds a manifest hashing to {found}")
    stamp = now()
    rows = _rows(snapshot, records, stamp)
    key = _state_key(rows)
    name = f"federation:{snapshot}"
    with board.writer():
        ensure_table(board)
        stored = board.one("SELECT key FROM projection_state WHERE name=?", (name,))
        counts = {"claims": len(records["claims"]), "artifacts": len(records["artifacts"]),
                  "citations": len(records["citations"])}
        if stored and stored["key"] == key:
            return {"snapshot": snapshot, **counts, "changed": False}
        with board.db:
            board.db.execute("DELETE FROM federation_record WHERE snapshot=?", (snapshot,))
            board.db.executemany("INSERT INTO federation_record(snapshot,record,kind,post,path,sha256,body,indexed) "
                                 "VALUES(?,?,?,?,?,?,?,?)", rows)
            board.db.execute("INSERT INTO projection_state(name,key,updated) VALUES(?,?,?) "
                             "ON CONFLICT(name) DO UPDATE SET key=excluded.key, updated=excluded.updated",
                             (name, key, stamp))
            board.event("federation_indexed", {"snapshot": snapshot, **counts, "records_from": records["derived"],
                                               **({"source": source} if source else {}),
                                               **({"actor": actor} if actor else {})})
    return {"snapshot": snapshot, **counts, "changed": True}


def reindex(board, actor):
    """Rebuild the whole index from `<commons>/federation/` (permission `import`; attributed to `actor`).
    Snapshots that no longer verify or no longer exist lose their rows; the result lists them."""
    from daw.commons.permissions import require
    actor = require(board, board.agent(actor), "import")["id"]
    folder = Path(board.root) / "federation"
    present = sorted(p.name for p in folder.iterdir() if p.is_dir() and re.match(r"^[0-9a-f]{64}$", p.name)) \
        if folder.is_dir() else []
    out, refused = [], []
    for snapshot in present:
        try:
            out.append(index_snapshot(board, snapshot, actor=actor))
        except DawError as error:
            refused.append({"snapshot": snapshot, "problem": f"{error.reason}: {error.detail}"})
    keep = {r["snapshot"] for r in out}
    with board.writer():
        ensure_table(board)
        stale = [r["snapshot"] for r in board.rows("SELECT DISTINCT snapshot FROM federation_record") if r["snapshot"] not in keep]
        if stale:
            with board.db:
                for snapshot in stale:
                    board.db.execute("DELETE FROM federation_record WHERE snapshot=?", (snapshot,))
                    board.db.execute("DELETE FROM projection_state WHERE name=?", (f"federation:{snapshot}",))
                board.event("federation_indexed", {"removed": stale, "actor": actor})
    return {"indexed": out, "refused": refused, "removed": stale}


def import_and_index(board, source, *, actor, expect=None, origin=None):
    """Verify and store a snapshot directory read-only, then index it. `actor` (name or id, permission
    `import`) is the importing participant: named in the receipt and the index event, and one
    `snapshot_imported` event per import act (spec v3 B9)."""
    from daw.commons import export
    from daw.commons.permissions import require
    person = require(board, board.agent(actor), "import")
    info = export.import_snapshot(board.root, source, expect=expect, importer=person["id"])
    index = index_snapshot(board, info["snapshot"], source=origin, actor=person["id"])
    with board.writer(), board.db:
        board.event("snapshot_imported", {"snapshot": info["snapshot"], "actor": person["id"],
                                          "already_imported": info["already_imported"], "scope": info.get("scope"),
                                          "counts": info.get("counts"),
                                          "index": {k: index[k] for k in ("claims", "artifacts", "citations", "changed")},
                                          **({"source": origin} if origin else {})})
    return {**info, "importer": person["id"], "index": index}


# ---------------------------------------------------------------------------- reads (never write)

def _query(view, sql, params=()):
    try:
        return view.rows(sql, params)
    except sqlite3.OperationalError:
        return []  # a board opened read-only before the table existed: nothing is indexed


def lookup(view, snapshot, record):
    rows = _query(view, "SELECT * FROM federation_record WHERE snapshot=? AND record=?", (snapshot, record))
    if not rows:
        return None
    row = dict(rows[0])
    row["body"] = json.loads(row["body"])
    return row


def indexed(view):
    """{snapshot: {claims, artifacts}} counts from the index."""
    out = {}
    for row in _query(view, "SELECT snapshot,kind,count(*) AS n FROM federation_record GROUP BY snapshot,kind"):
        out.setdefault(row["snapshot"], {"claims": 0, "artifacts": 0, "citations": 0})[row["kind"] + "s"] = row["n"]
    return out


def records(view, snapshot):
    """Indexed claims, artifacts and outgoing citations of one snapshot, as foreign untrusted data with byte
    routes. A citation says whether it names a snapshot this board exported (`cites_this_commons`)."""
    out = {"claims": [], "artifacts": [], "citations": []}
    own = own_snapshots(view)
    for row in _query(view, "SELECT * FROM federation_record WHERE snapshot=? ORDER BY kind,record", (snapshot,)):
        body = json.loads(row["body"])
        if row["kind"] == "citation":
            out["citations"].append({"post": row["post"], **body,
                                     "cited": pointer(body["cited_snapshot"], body["cited_record"]),
                                     "cites_this_commons": body["cited_snapshot"] in own})
            continue
        entry = {"id": row["record"], "pointer": pointer(snapshot, row["record"]), **body}
        if row["kind"] == "claim":
            entry["post"] = row["post"]
            out["claims"].append(entry)
        else:
            entry.update(sha256=row["sha256"], path=row["path"],
                         bytes_url=f"/api/federation/{snapshot}/files/{row['path']}" if row["path"] else None)
            out["artifacts"].append(entry)
    return out


def resolve(view, identity, kind):
    """What a foreign pointer opens (shape of `writeup.resolve_pointer` entries): foreign, untrusted."""
    entry = {"id": identity, "kind": kind, "present": False, "foreign": True}
    parts = split(identity)
    if not parts:
        return entry
    snapshot, record = parts
    entry.update(snapshot=snapshot, record=record, route=f"/directory/{snapshot}#{record}")
    row = lookup(view, snapshot, record)
    if not row or row["kind"] != kind:
        entry["reason"] = "not in this commons' federation index (import the snapshot first)"
        return entry
    body = row["body"]
    if kind == "claim":
        entry.update(present=True, text=body.get("text"), status=body.get("status"), scope=body.get("scope") or {},
                     post=row["post"], post_title=body.get("post_title"), stated_status=body.get("status"),
                     pointers=[{**p, "foreign": True} for p in body.get("pointers") or []], withdrawn_by=None,
                     foreign_withdrawn_by=body.get("withdrawn_by"), marks=[], author=None, author_name=None)
    else:
        entry.update(present=True, title=body.get("title"), output_role=body.get("output_role"),
                     derivation_key=body.get("derivation_key"), sha256=row["sha256"], name=body.get("name"),
                     size=body.get("bytes"), location={"store": "federation", "snapshot": snapshot},
                     bytes_present=bool(row["path"]),
                     bytes_url=f"/api/federation/{snapshot}/files/{row['path']}" if row["path"] else None,
                     image_url=None)
    return entry


def artifact_output(view, identity):
    """(bytes or None, name, reason) of a foreign artifact's output, read from the stored snapshot and checked
    against the hash its manifest lists (the same contract as `locators.artifact_output`)."""
    parts = split(identity)
    row = lookup(view, *parts) if parts else None
    if not row or row["kind"] != "artifact":
        return None, None, "not in this commons' federation index (import the snapshot first)"
    name = row["body"].get("name")
    if not row["path"]:
        return None, name, "the output bytes are not in the snapshot (present: false)"
    path = Path(view.root) / "federation" / parts[0] / row["path"]
    if path.is_symlink() or not path.is_file():
        return None, name, "the snapshot's stored copy is missing this file"
    if path.stat().st_size > READ_LIMIT:
        return None, name, "the output is larger than 32 MB and is not read for checks"
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != row["sha256"]:
        return None, name, "the stored bytes do not match the snapshot manifest's sha256"
    return data, name, None


# ---------------------------------------------------------------------------- citations (dashboard)

def own_snapshots(view):
    """Snapshot ids this board exported (its `snapshot_exported` and `preprint_exported` events)."""
    rows = view.rows("SELECT json_extract(body,'$.snapshot') AS snapshot FROM event "
                     "WHERE kind IN ('snapshot_exported','preprint_exported')")
    return {r["snapshot"] for r in rows if r["snapshot"]}


def cited_by(view, record=None):
    """Incoming citations: posts of imported snapshots whose text names a record of a snapshot this board
    exported, as indexed (recorded at the citing source, backed by the citing snapshot's bytes). Restricted to
    one local record (`claim_…`, `artifact_…`) when given. Foreign, untrusted data. Reads only."""
    own = own_snapshots(view)
    if not own:
        return []
    out = []
    for row in _query(view, "SELECT * FROM federation_record WHERE kind='citation' ORDER BY snapshot,record"):
        body = json.loads(row["body"])
        if body.get("cited_snapshot") not in own or (record and body.get("cited_record") != record):
            continue
        out.append({"snapshot": row["snapshot"], "post": row["post"], "post_title": body.get("post_title"),
                    "author": body.get("author"), "created": body.get("created"),
                    "record": body["cited_record"], "kind": body.get("cited_kind"),
                    "cited": pointer(body["cited_snapshot"], body["cited_record"]),
                    "cited_snapshot": body["cited_snapshot"], "route": f"/directory/{row['snapshot']}#{row['post']}",
                    "foreign": True})
    return out


def citations(view):
    """Recorded citations of foreign snapshots: posts whose text names `snapshot:<id>/…`, grouped by snapshot,
    with the citing question (the notebook the post published) or thread. Hidden and withheld posts count
    nothing. Reads only."""
    from daw.commons import views
    index = views.thread_index(view)
    vis = views.visibility(view)
    known = indexed(view)
    imported = {p.name for p in (Path(view.root) / "federation").iterdir()} if (Path(view.root) / "federation").is_dir() else set()
    groups = {}
    for pid, row in index["posts"].items():
        if vis.withheld(pid) or vis.refused(pid):
            continue
        content = row["content"]
        found = FOREIGN.findall(content.get("body") or "")
        if not found:
            continue
        notebook = (content.get("evidence") or {}).get("notebook")
        question = f"{row['author']}/{notebook['question']}" if isinstance(notebook, dict) and notebook.get("question") else None
        for snapshot, record in dict.fromkeys(found):
            group = groups.setdefault(snapshot, {"snapshot": snapshot, "imported": snapshot in imported,
                                                 "indexed": known.get(snapshot), "citations": [], "questions": {}})
            resolves = bool(lookup(view, snapshot, record))
            group["citations"].append({"post": pid, "record": record, "author": row["author"], "question": question,
                                       "thread": index["roots"].get(pid), "resolves": resolves,
                                       "created": row["created"]})
            label = question or f"thread {index['roots'].get(pid)}"
            group["questions"].setdefault(label, {"question": question, "thread": None if question else index["roots"].get(pid),
                                                  "posts": [], "records": []})
            entry = group["questions"][label]
            if pid not in entry["posts"]:
                entry["posts"].append(pid)
            if record not in entry["records"]:
                entry["records"].append(record)
    out = []
    for snapshot in sorted(groups):
        group = groups[snapshot]
        group["questions"] = sorted(group["questions"].values(), key=lambda q: (q["question"] or "~", q["thread"] or ""))
        group["citing_posts"] = len({c["post"] for c in group["citations"]})
        out.append(group)
    incoming = {}
    for item in cited_by(view):
        group = incoming.setdefault(item["snapshot"], {"snapshot": item["snapshot"], "citations": []})
        group["citations"].append({**item, "here": _here(view, item["record"])})
    return {"snapshots": out, "cited_by": [incoming[s] for s in sorted(incoming)], "sequence": view.sequence(),
            "note": "Recorded citations only: posts whose text names snapshot:<id>/<record>. A question is the "
                    "notebook a citing post published; otherwise its thread is shown. Hidden posts and withheld "
                    "write-ups are not counted. Cited by: posts of imported snapshots naming a record of a "
                    "snapshot this board exported (learned by importing the citing snapshot)."}


def _here(view, record):
    """Whether a cited record exists on this board (a claim row or a library artifact)."""
    if record.startswith("claim_"):
        return bool(view.one("SELECT id FROM claim WHERE id=?", (record,)))
    return bool(view.library.one("SELECT id FROM artifact WHERE id=?", (record,)))
