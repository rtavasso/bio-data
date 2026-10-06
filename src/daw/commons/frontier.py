"""Frontier index (M1.7), frontier browser reads (M5.1) and dataset wishlist (M5.4).

Open items are agent-authored and live in the question's own workspace as work
events: `frontier_item` (open question, untestable branch, gap, proposed
experiment, next computable step) and append-only `frontier_item_status`.
Retrieval gaps (`retrieval_gap`, minus withdrawals) are items of kind gap. The
platform only indexes them: `rebuild_frontier` scans every participant workspace
read-only and upserts the board's `frontier_item` projection. The board owns only
`promoted_to` and the statuses set by promotions ("promoted") and watchers
("candidate_evidence"); an agent's closed/withdrawn status always wins.

Clustering of "the same experiment proposed by several questions" is exact-term
overlap (normalized token sets, Jaccard), shown as a suggestion with its shared
terms; a person's confirmation is an attribution event, never a merge. The
wishlist groups exact "missing measurement" statements by normalized text with
no synonym merging.
"""
import json
import re
from itertools import combinations
from pathlib import Path

from daw.commons.archive import ReadOnlyWorkspace
from daw.commons.claims import ACCESSIONS, ARTIFACT_ID, BLOB, POINTER_KINDS, POST_ID
from daw.commons.permissions import require
from daw.search import index_document
from daw.util import DawError, canonical, digest, now, read_json

KINDS = ("open_question", "untestable", "gap", "proposed_experiment", "next_step")
AGENT_STATUSES = ("open", "candidate_evidence", "closed", "withdrawn")
BOARD_STATUSES = ("promoted", "candidate_evidence")
STATUSES = ("open", "candidate_evidence", "promoted", "closed", "withdrawn")
ITEM_FIELDS = {"kind", "text", "blocked_by", "watcher_query", "missing_measurement", "pointers", "key", "post", "question"}
CLUSTER_KINDS = ("proposed_experiment", "next_step")
CLUSTER_THRESHOLD = 0.5
MISSING_LINE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?Exact missing measurement:\s*(.+?)\s*$", re.IGNORECASE)
STOPWORDS = frozenset("""a an and are as at be by for from has have in into is it its of on or per that the their then
this to was were whether which with within using use whose than vs versus can could should would may might""".split())


def _text(payload, field, limit, *, required=False):
    value = payload.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise DawError("invalid_frontier_item", f"{field} must be nonempty text up to {limit} characters")
    return value.strip()


def parse_pointer(value):
    """`kind:id` or `kind:id#locator` (CLI form) or a {kind, id, locator?} object."""
    if isinstance(value, str):
        kind, sep, rest = value.partition(":")
        if not sep:
            raise DawError("invalid_frontier_pointer", "use kind:id")
        identity, _, locator = rest.partition("#")
        value = {"kind": kind, "id": identity, **({"locator": locator} if locator else {})}
    if not isinstance(value, dict) or set(value) - {"kind", "id", "locator"}:
        raise DawError("invalid_frontier_pointer", "use {kind, id, locator?}")
    return value


def check_workspace_pointer(ws, pointer):
    """Pointers in a question's own workspace must resolve there. Post ids are checked for form only
    (a workspace cannot see the board); the board projection marks whether they exist."""
    pointer = parse_pointer(pointer)
    kind, identity = pointer.get("kind"), pointer.get("id")
    if kind not in POINTER_KINDS or not isinstance(identity, str) or not identity:
        raise DawError("invalid_frontier_pointer", f"kind must be one of {', '.join(POINTER_KINDS)}")

    def blob(sha):
        return bool(BLOB.fullmatch(sha) and ws.one("SELECT sha256 FROM blob WHERE sha256=?", (sha,)))

    def artifact(aid):
        return bool(ARTIFACT_ID.fullmatch(aid) and ws.one("SELECT id FROM artifact WHERE id=?", (aid,)))

    ok = {"artifact": lambda: artifact(identity), "receipt": lambda: blob(identity),
          "post": lambda: bool(POST_ID.fullmatch(identity)), "accession": lambda: bool(ACCESSIONS.fullmatch(identity)),
          "locator": lambda: bool(pointer.get("locator")) and (blob(identity) or artifact(identity)
                                                              or bool(POST_ID.fullmatch(identity)))}[kind]()
    if not ok:
        raise DawError("frontier_pointer_unresolved", f"{kind}:{identity}")
    return {k: v for k, v in pointer.items() if v}


def validate_item(ws, payload, question):
    if not isinstance(payload, dict):
        raise DawError("invalid_frontier_item", "use a JSON object")
    unknown = set(payload) - ITEM_FIELDS
    if unknown:
        raise DawError("invalid_frontier_item", f"unknown fields {', '.join(sorted(unknown))}")
    if payload.get("question", question) != question:
        raise DawError("frontier_question_mismatch")
    if payload.get("kind") not in KINDS:
        raise DawError("invalid_frontier_kind", ", ".join(KINDS))
    query = payload.get("watcher_query")
    if query is not None and not ((isinstance(query, str) and query.strip() and len(query) <= 2000)
                                  or (isinstance(query, dict) and query and len(canonical(query)) <= 4000)):
        raise DawError("invalid_frontier_item", "watcher_query is text or a JSON object")
    pointers = payload.get("pointers") or []
    if not isinstance(pointers, list) or len(pointers) > 50:
        raise DawError("invalid_frontier_item", "pointers is a list (at most 50)")
    post = payload.get("post")
    if post is not None and not (isinstance(post, str) and POST_ID.fullmatch(post)):
        raise DawError("invalid_frontier_item", "post is a post identifier")
    clean = {"question": question, "kind": payload["kind"], "text": _text(payload, "text", 4000, required=True),
             "blocked_by": _text(payload, "blocked_by", 1000), "missing_measurement": _text(payload, "missing_measurement", 1000),
             "key": _text(payload, "key", 200), "post": post,
             "watcher_query": query.strip() if isinstance(query, str) else query,
             "pointers": [check_workspace_pointer(ws, p) for p in pointers]}
    return {k: v for k, v in clean.items() if v not in (None, [])}


def validate_status(ws, payload, question):
    if not isinstance(payload, dict) or set(payload) - {"item", "status", "reason", "question"}:
        raise DawError("invalid_frontier_status", "use {item, status, reason}")
    if payload.get("status") not in AGENT_STATUSES:
        raise DawError("invalid_frontier_status", ", ".join(AGENT_STATUSES))
    reason = _text(payload, "reason", 2000, required=True)
    target = ws.one("SELECT * FROM work_event WHERE id=?", (payload.get("item"),)) if isinstance(payload.get("item"), str) else None
    if not target or target["kind"] not in ("frontier_item", "retrieval_gap") or target["question_id"] != question:
        raise DawError("invalid_frontier_status_target", "name a frontier_item or retrieval_gap event of this question")
    return {"question": question, "item": payload["item"], "status": payload["status"], "reason": reason}


def parse_items(ws, question, value):
    """Validate a list of items (publish --frontier) without recording; returns record_item keyword sets."""
    if isinstance(value, dict) and "items" in value:
        value = value["items"]
    if not isinstance(value, list) or not 1 <= len(value) <= 100:
        raise DawError("invalid_frontier_item", "supply a list of 1 to 100 items")
    return [{k: v for k, v in validate_item(ws, item, question).items() if k != "question"} for item in value]


def _events(ws, kinds, question=None):
    sql = f"SELECT * FROM work_event WHERE kind IN ({','.join('?' for _ in kinds)})"
    params = list(kinds)
    if question:
        sql += " AND question_id=?"
        params.append(question)
    return ws.rows(sql + " ORDER BY created,id", params)


def record_item(ws, question, *, kind, text, blocked_by=None, watcher_query=None, missing_measurement=None,
                pointers=(), key=None, post=None):
    """Record one open item in the caller's own question. Caller holds the workspace writer lock.
    With `key`, a retry returns the existing event; different content under the same key is a conflict."""
    from daw.work import record_event
    payload = validate_item(ws, {"kind": kind, "text": text, "blocked_by": blocked_by, "watcher_query": watcher_query,
                                 "missing_measurement": missing_measurement, "pointers": list(pointers), "key": key,
                                 "post": post}, question)
    if key:
        for event in _events(ws, ("frontier_item",), question):
            previous = read_json(ws.blob_path(event["body_blob"]))
            if previous.get("key") == key:
                if previous != payload:
                    raise DawError("frontier_key_conflict", key)
                return {"id": event["id"], "question": question, "kind": event["kind"],
                        "body_blob": event["body_blob"], "created": event["created"], "reused": True}
    return record_event(ws, question, "frontier_item", payload)


def record_status(ws, question, item, status, reason):
    """Append a status event for an item (or a retrieval gap). Caller holds the workspace writer lock."""
    from daw.work import record_event
    return record_event(ws, question, "frontier_item_status", {"item": item, "status": status, "reason": reason})


def workspace_items(ws, question=None):
    """Items of one workspace with their latest agent-recorded status (append-only events, last wins)."""
    from daw.gaps import validate_gap
    items = {}
    events = _events(ws, ("frontier_item", "retrieval_gap", "frontier_item_status", "retrieval_gap_withdrawal"), question)
    for event in events:
        payload = read_json(ws.blob_path(event["body_blob"]))
        qid = event["question_id"]
        try:
            if event["kind"] == "frontier_item":
                item = payload  # validated by record_event when it was written
                if not isinstance(item, dict) or item.get("kind") not in KINDS or not isinstance(item.get("text"), str):
                    continue
                items[event["id"]] = {
                    "event": event["id"], "question": qid, "kind": item["kind"], "text": item["text"],
                    "blocked_by": item.get("blocked_by"), "watcher_query": item.get("watcher_query"),
                    "missing_measurement": item.get("missing_measurement"), "pointers": item.get("pointers", []),
                    "key": item.get("key"), "post": item.get("post"), "event_kind": "frontier_item",
                    "body_blob": event["body_blob"], "created": event["created"], "status": "open",
                    "status_time": event["created"], "status_reason": None, "detail": {}}
            elif event["kind"] == "retrieval_gap":
                gap = validate_gap(payload, qid)
                items[event["id"]] = {
                    "event": event["id"], "question": qid, "kind": "gap", "text": gap["desired_information"],
                    "blocked_by": gap.get("blocked_by") or f"retrieval gap ({gap['source_or_format']})",
                    "watcher_query": gap.get("watcher_query"), "missing_measurement": None,
                    "pointers": [{"kind": "receipt", "id": gap["evidence_blob"]}] if gap.get("evidence_blob") else [],
                    "key": gap.get("gap_key"), "post": None, "event_kind": "retrieval_gap",
                    "body_blob": event["body_blob"], "created": event["created"], "status": "open",
                    "status_time": event["created"], "status_reason": None,
                    "detail": {k: gap[k] for k in ("why_current_tools_failed", "source_or_format",
                                                   "possible_indexing_solution", "likely_value") if gap.get(k)}}
            else:
                target = payload.get("item", payload.get("event")) if isinstance(payload, dict) else None
                if target in items:
                    status = "withdrawn" if event["kind"] == "retrieval_gap_withdrawal" else payload.get("status")
                    if status in AGENT_STATUSES:
                        items[target].update(status=status, status_time=event["created"],
                                             status_reason=payload.get("reason"), status_event=event["id"])
        except DawError:
            continue  # pre-v3 freeform events stay in the notebook; they are not frontier items
    return list(items.values())


def item_id(author, event):
    return "frontier_" + digest([author, event])[:32]


def _workspace_path(root, agent):
    relative = Path(agent["trial"])
    path = (root / relative / "workspace").resolve()
    if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(root / "agents"):
        raise DawError("unsafe_agent_path")
    return path


def workspaces(owner):
    """(agent, read-only workspace) for every participant with a research checkout, oldest first."""
    for agent in owner.rows("SELECT id,name,trial,parent,created FROM agent WHERE trial IS NOT NULL ORDER BY created,id"):
        path = _workspace_path(owner.root, agent)
        if not (path / "catalog.sqlite").is_file():
            continue
        ws = ReadOnlyWorkspace(path)
        try:
            yield agent, ws
        finally:
            ws.close()


def refresh_key(owner):
    """Cheap change check: last board event plus each workspace's work-event count and latest time."""
    sequence = owner.one("SELECT coalesce(max(seq),0) AS n FROM event")["n"]
    counts = []
    for agent, ws in workspaces(owner):
        row = ws.one("SELECT count(*) AS n,coalesce(max(created),'') AS m FROM work_event")
        counts.append([agent["id"], row["n"], row["m"]])
    return f"{sequence}:{digest(counts)[:32]}"


def stored_key(owner, name="frontier"):
    try:
        row = owner.one("SELECT key FROM projection_state WHERE name=?", (name,))
    except Exception:  # an archive opened before the board gained the bookkeeping table
        return None
    return row["key"] if row else None


def _status(agent_item, existing):
    """Agent closed/withdrawn wins; then board-owned promoted; then a board candidate_evidence newer than the
    agent's latest status; otherwise the agent's status. Returns (status, updated)."""
    status, when = agent_item["status"], agent_item["status_time"]
    if status in ("closed", "withdrawn") or not existing:
        return status, when
    if existing["status"] == "promoted" or existing["promoted_to"]:
        return "promoted", existing["updated"]
    if existing["status"] == "candidate_evidence" and when <= existing["updated"]:
        return "candidate_evidence", existing["updated"]
    return status, when


COLUMNS = ("question", "author", "workspace", "kind", "text", "status", "blocked_by", "watcher_query",
           "pointers", "source", "created", "updated")


def _board_watcher(value):
    try:
        return isinstance(json.loads(value), dict) and "watcher" in json.loads(value)
    except (TypeError, ValueError):
        return False


def rebuild_frontier(board):
    """Upsert the frontier projection from every participant workspace (read-only). Idempotent.
    A fork's inherited items (same question and event as an older participant) stay attributed to the
    original author; the fork's status events on inherited items are not applied."""
    with board.writer(), board.library.writer():
        owners, computed, inherited = {}, [], 0
        for agent, ws in workspaces(board):
            for item in workspace_items(ws):
                if owners.setdefault((item["question"], item["event"]), agent["id"]) != agent["id"]:
                    inherited += 1
                    continue
                computed.append((agent, item))
        existing = {r["id"]: r for r in board.rows("SELECT * FROM frontier_item")}
        inserted, updated, changed = 0, 0, []
        with board.db:
            for agent, item in computed:
                identity = item_id(agent["id"], item["event"])
                old = existing.get(identity)
                status, when = _status(item, old)
                # A watcher attached on the board (daw.commons.watchers) owns watcher_query, like promoted_to;
                # the agent-authored query is used only while no watcher is attached.
                query = old["watcher_query"] if old and old["watcher_query"] and _board_watcher(old["watcher_query"]) \
                    else item["watcher_query"]
                source = {"event": item["event"], "event_kind": item["event_kind"], "body_blob": item["body_blob"],
                          "missing_measurement": item["missing_measurement"], "key": item["key"], "post": item["post"],
                          "status_event": item.get("status_event"), "status_reason": item["status_reason"],
                          "agent_status": item["status"], "detail": item["detail"]}
                values = {"question": item["question"], "author": agent["id"],
                          "workspace": str(Path(agent["trial"]) / "workspace"), "kind": item["kind"], "text": item["text"],
                          "status": status, "blocked_by": item["blocked_by"],
                          "watcher_query": None if query is None else query if isinstance(query, str) else canonical(query).decode(),
                          "pointers": canonical(item["pointers"]).decode(), "source": canonical(source).decode(),
                          "created": item["created"], "updated": when}
                if old and all(old[c] == values[c] for c in COLUMNS):
                    continue
                if old:
                    board.db.execute("UPDATE frontier_item SET " + ",".join(f"{c}=?" for c in COLUMNS) + " WHERE id=?",
                                     [values[c] for c in COLUMNS] + [identity])
                    updated += 1
                else:
                    board.db.execute("INSERT INTO frontier_item(id," + ",".join(COLUMNS) + ",promoted_to) VALUES(?,"
                                     + ",".join("?" for _ in COLUMNS) + ",NULL)", [identity] + [values[c] for c in COLUMNS])
                    inserted += 1
                changed.append({"id": identity, **values})
        for row in changed:
            blob = board.library.put_json({"format": "daw.frontier_item/1", **row})
            index_document(board.library, key="frontier:" + row["id"], family="frontier", subject=row["id"],
                           record_id=row["id"], title=row["text"][:200], summary=row["text"][:2000], body_blob=blob,
                           detail={"kind": row["kind"], "status": row["status"], "blocked_by": row["blocked_by"],
                                   "question": row["question"], "author": row["author"],
                                   "missing_measurement": json.loads(row["source"]).get("missing_measurement")},
                           provider="community", level=3)
        current = {item_id(agent["id"], item["event"]) for agent, item in computed}
        summary = {"items": len(computed), "inserted": inserted, "updated": updated, "inherited_skipped": inherited,
                   "orphaned": sorted(set(existing) - current)}
        with board.db:
            if inserted or updated:
                board.event("frontier_reindexed", {k: v for k, v in summary.items() if k != "orphaned"})
            key = refresh_key(board)
            board.db.execute("INSERT INTO projection_state(name,key,updated) VALUES('frontier',?,?) "
                             "ON CONFLICT(name) DO UPDATE SET key=excluded.key,updated=excluded.updated", (key, now()))
        return {**summary, "key": key}


def ensure_current(root, view):
    """Refresh the projection before an API read when the board or any workspace changed."""
    if stored_key(view) == refresh_key(view):
        return None
    from daw.community import Community
    with Community(root) as board:
        return rebuild_frontier(board)


def tokens(text):
    return frozenset(t for t in re.findall(r"[a-z0-9]+", (text or "").casefold()) if len(t) > 1 and t not in STOPWORDS)


def clusters(items, *, threshold=CLUSTER_THRESHOLD, kinds=CLUSTER_KINDS, confirmations=()):
    """Exact-term overlap suggestions across different questions. Never merges items."""
    live = [i for i in items if i["kind"] in kinds and i["status"] not in ("closed", "withdrawn")]
    terms = {i["id"]: tokens(i["text"]) for i in live}
    parent = {i["id"]: i["id"] for i in live}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs = []
    for a, b in combinations(live, 2):
        if a["kind"] != b["kind"] or a["question"] == b["question"]:
            continue
        ta, tb = terms[a["id"]], terms[b["id"]]
        if not ta or not tb:
            continue
        score = len(ta & tb) / len(ta | tb)
        if score >= threshold:
            pairs.append({"items": [a["id"], b["id"]], "jaccard": round(score, 3), "shared_terms": sorted(ta & tb)})
            parent[find(a["id"])] = find(b["id"])
    groups = {}
    for pair in pairs:
        groups.setdefault(find(pair["items"][0]), []).append(pair)
    by_id = {i["id"]: i for i in live}
    output = []
    for group in groups.values():
        ids = sorted({x for p in group for x in p["items"]})
        shared = frozenset.intersection(*(terms[x] for x in ids))
        output.append({"id": "cluster_" + digest(ids)[:24], "kind": by_id[ids[0]]["kind"], "items": ids,
                       "questions": sorted({by_id[x]["question"] for x in ids}), "shared_terms": sorted(shared),
                       "pairs": group, "confirmations": [c for c in confirmations if set(c["items"]) <= set(ids)],
                       "basis": f"normalized token sets, Jaccard >= {threshold}, different questions; a suggestion only"})
    output.sort(key=lambda c: (-len(c["questions"]), c["id"]))
    return output


def confirmations(owner):
    return [{"seq": r["seq"], "created": r["created"], **json.loads(r["body"])}
            for r in owner.rows("SELECT seq,body,created FROM event WHERE kind='frontier_cluster_confirmed' ORDER BY seq")]


def confirm_cluster(board, actor, items, note=""):
    """A person confirms that items describe the same experiment. Attribution only: one event, no merge."""
    participant = require(board, board.agent(actor), "mark")
    items = sorted(set(items or []))
    if len(items) < 2 or len(items) > 50:
        raise DawError("invalid_cluster", "confirm 2 to 50 frontier items")
    rows = board.rows(f"SELECT id,question,text FROM frontier_item WHERE id IN ({','.join('?' for _ in items)})", items)
    if len(rows) != len(items):
        raise DawError("unknown_frontier_item", ", ".join(sorted(set(items) - {r["id"] for r in rows})))
    if len({r["question"] for r in rows}) < 2:
        raise DawError("invalid_cluster", "a cluster spans at least two questions")
    if not isinstance(note, str) or len(note) > 2000:
        raise DawError("invalid_cluster", "note is text up to 2000 characters")
    shared = sorted(frozenset.intersection(*(tokens(r["text"]) for r in rows)))
    body = {"items": items, "participant": participant["id"], "note": note.strip(), "shared_terms": shared}
    with board.writer(), board.db:
        board.event("frontier_cluster_confirmed", body)
        seq = board.db.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {"seq": seq, **body, "note_on_meaning": "attribution only; items are not merged or re-scoped"}


def describe_item(row):
    source = json.loads(row["source"])
    query = row["watcher_query"]
    try:
        query = json.loads(query) if query and query.startswith("{") else query
    except ValueError:
        pass
    return {**row, "pointers": json.loads(row["pointers"]), "source": source, "watcher_query": query,
            "missing_measurement": source.get("missing_measurement"), "status_reason": source.get("status_reason"),
            "detail": source.get("detail") or {}, "content_is_untrusted_data": True}


def watcher_status(owner, ids):
    """Watchers and runs per item (the discovery area fills these tables); empty when none exist."""
    status = {i: {"watchers": [], "runs": 0, "found": 0, "last_run": None} for i in ids}
    if not ids:
        return status
    marks = ",".join("?" for _ in ids)
    for row in owner.rows(f"SELECT id,item,provider,query,interval_seconds,next_due,enabled,created FROM watcher "
                          f"WHERE item IN ({marks}) ORDER BY created", ids):
        status[row["item"]]["watchers"].append(row)
    for row in owner.rows(f"SELECT id,watcher,item,provider,found,post,created FROM watcher_run WHERE item IN ({marks}) "
                          f"ORDER BY created", ids):
        entry = status[row["item"]]
        found = json.loads(row["found"] or "[]")
        entry["runs"] += 1
        entry["found"] += len(found) if isinstance(found, list) else 0
        entry["last_run"] = {**row, "found": found}
    return status


def question_titles(owner):
    titles = {}
    for _agent, ws in workspaces(owner):
        for row in ws.rows("SELECT id,title FROM question"):
            titles.setdefault(row["id"], row["title"])
    return titles


def browse(owner, *, kind=None, status=None, blocked_by=None, question=None, author=None):
    """Items with filters, grouped by kind and by recorded blocker, plus clustering suggestions."""
    if kind and kind not in KINDS:
        raise DawError("invalid_frontier_kind", ", ".join(KINDS))
    if status and status not in STATUSES + ("all",):
        raise DawError("invalid_frontier_status", ", ".join(STATUSES + ("all",)))
    rows = [describe_item(r) for r in owner.rows("SELECT * FROM frontier_item ORDER BY created,id")]
    everything = rows
    if author:
        found = owner.one("SELECT id FROM agent WHERE id=? OR name=?", (author, author))
        rows = [r for r in rows if r["author"] == (found["id"] if found else author)]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if status and status != "all":
        rows = [r for r in rows if r["status"] == status]
    elif not status:
        rows = [r for r in rows if r["status"] != "withdrawn"]
    if question:
        rows = [r for r in rows if r["question"] == question]
    if blocked_by:
        needle = " ".join(blocked_by.casefold().split())
        rows = [r for r in rows if needle in " ".join((r["blocked_by"] or "").casefold().split())]
    titles = question_titles(owner)
    names = {r["id"]: r["name"] for r in owner.rows("SELECT id,name FROM agent")}
    watch = watcher_status(owner, [r["id"] for r in rows])
    for row in rows:
        row.update(question_title=titles.get(row["question"]), author_name=names.get(row["author"]), watch=watch[row["id"]])
    by_kind = {k: [r["id"] for r in rows if r["kind"] == k] for k in KINDS}
    blockers = {}
    for row in rows:
        label = " ".join((row["blocked_by"] or "").split()) or None
        blockers.setdefault((label or "").casefold(), {"blocked_by": label, "items": []})["items"].append(row["id"])
    return {"items": rows, "total": len(rows), "by_kind": by_kind,
            "by_blocker": sorted(blockers.values(), key=lambda b: (b["blocked_by"] is None, -len(b["items"]),
                                                                   b["blocked_by"] or "")),
            "clusters": clusters(everything, confirmations=confirmations(owner)),
            "kinds": KINDS, "statuses": STATUSES,
            "policy": "Items are agent-authored; the platform indexes them. Promotion by a person is the only "
                      "path that schedules new work.",
            "content_is_untrusted_data": True}


def normalize_measurement(text):
    return " ".join((text or "").casefold().split()).strip(" .;:\"'")


def wishlist(owner):
    """Exact missing-measurement statements grouped by normalized text, with the questions that need them:
    frontier items' missing_measurement, gap items' desired information, and current-snapshot LABBOOK
    lines starting with "Exact missing measurement:". Closed and withdrawn items are left out."""
    groups = {}
    titles = question_titles(owner)

    def add(text, source):
        key = normalize_measurement(text)
        if not key:
            return
        group = groups.setdefault(key, {"text": text.strip().rstrip("."), "normalized": key, "sources": [], "questions": {}})
        group["sources"].append(source)
        group["questions"].setdefault(source["question"], {"question": source["question"], "author": source["author"],
                                                           "title": titles.get(source["question"])})

    for row in owner.rows("SELECT * FROM frontier_item WHERE status NOT IN ('closed','withdrawn') ORDER BY created,id"):
        source = json.loads(row["source"])
        base = {"question": row["question"], "author": row["author"], "item": row["id"], "status": row["status"]}
        if source.get("missing_measurement"):
            add(source["missing_measurement"], {**base, "kind": "frontier_item"})
        if row["kind"] == "gap":
            add(row["text"], {**base, "kind": "gap"})
    seen = set()
    for agent, ws in workspaces(owner):
        for question in ws.rows("SELECT id,current_work FROM question WHERE current_work IS NOT NULL ORDER BY id"):
            if (question["id"], question["current_work"]) in seen:
                continue  # a fork's unchanged copy of an inherited notebook
            seen.add((question["id"], question["current_work"]))
            snapshot = ws.one("SELECT body_blob FROM work_snapshot WHERE id=?", (question["current_work"],))
            files = read_json(ws.blob_path(snapshot["body_blob"])).get("files", {}) if snapshot else {}
            if "LABBOOK.md" not in files:
                continue
            text = ws.blob_path(files["LABBOOK.md"]).read_text(errors="replace")
            for number, line in enumerate(text.splitlines(), 1):
                match = MISSING_LINE.match(line)
                if match:
                    add(match.group(1), {"question": question["id"], "author": agent["id"], "kind": "labbook",
                                         "snapshot": question["current_work"], "line": number})
    names = {r["id"]: r["name"] for r in owner.rows("SELECT id,name FROM agent")}
    items = []
    for group in groups.values():
        questions = list(group["questions"].values())
        for q in questions:
            q["author_name"] = names.get(q["author"])
        items.append({**group, "questions": questions, "distinct_questions": len(questions)})
    items.sort(key=lambda g: (-g["distinct_questions"], g["normalized"]))
    return {"items": items, "total": len(items),
            "grouping": "normalized exact text (case, whitespace, trailing punctuation); no synonym merging",
            "content_is_untrusted_data": True}


def extend_demo(board, ctx):
    """Synthetic frontier items in three questions, with an overlapping proposed experiment (alice, bob),
    a shared missing measurement, an untestable branch and a closed item. Recorded from each agent's own
    workspace as `bio work frontier` would."""
    from daw.catalog import Workspace
    agents, questions = ctx["agents"], ctx["questions"]
    recorded = {}

    def record(name, *items, status=None):
        ws = Workspace(board.trial(board.agent(agents[name])) / "workspace")
        try:
            with ws.writer():
                for key, item in items:
                    recorded[key] = record_item(ws, questions[name], key="demo-" + key, **item)["id"]
                if status:
                    record_status(ws, questions[name], recorded[status[0]], status[1], status[2])
        finally:
            ws.close()

    record("alice",
           ("alice-qpcr", {"kind": "proposed_experiment", "missing_measurement": "Donor identity per sample.",
                           "text": "Measure the marker by qPCR in conditions A and B with donor-matched samples."}),
           ("alice-donors", {"kind": "next_step", "text": "Test donor structure once donor identity is recorded.",
                             "blocked_by": "donor identity per sample",
                             "pointers": [{"kind": "artifact", "id": ctx["artifacts"]["contrast"]}]}))
    record("bob",
           ("bob-qpcr", {"kind": "proposed_experiment", "missing_measurement": "donor identity per sample",
                         "text": "Measure the marker by qPCR in conditions A and B using donor-matched samples and a spike-in.",
                         "watcher_query": {"text": "demo marker spike-in qPCR", "provider": "geo"}}),
           ("bob-spikein", {"kind": "open_question", "text": "Is a spike-in available for the demo table?"}),
           status=("bob-spikein", "closed", "The synthetic table has no spike-in; recorded as a limitation."))
    record("dana",
           ("dana-untestable", {"kind": "untestable", "blocked_by": "Per-sample counts after marker knockdown",
                                "text": "Whether knockdown changes the marker cannot be tested without perturbation data.",
                                "pointers": [{"kind": "accession", "id": "GSE000001"}]}))
    ctx["frontier"] = {"events": recorded, "summary": rebuild_frontier(board),
                       "items": {k: item_id(agents[k.split("-")[0]], v) for k, v in recorded.items()}}
