"""Frontier index (M1.7), frontier browser reads (M5.1) and dataset wishlist (M5.4).

Open items are agent-authored and live in the question's own workspace as work
events: `frontier_item` (open question, untestable branch, gap, proposed
experiment, next computable step) and append-only `frontier_item_status`.
Retrieval gaps (`retrieval_gap`, minus withdrawals) are items of kind gap. The
platform only indexes them: `rebuild_frontier` scans every participant workspace
read-only and writes the board's `frontier_item` projection. Board-owned state is
derived from immutable board events, never stored only in the projection:
`promotion_created` (status "promoted", `promoted_to`), `watcher_added` and
`watcher_disabled` (the board watcher's query masks the author's while it is
enabled) and `watcher_ran` (status "candidate_evidence", `candidate_source`
"watcher"). An agent's own candidate_evidence status is attributed to the author;
an agent's closed/withdrawn status always wins. Dropping the table and rebuilding
reproduces it byte for byte; rows no record supports are deleted.

The projection is refreshed on the write path only (publication with frontier
items or a notebook, promotion, watcher events) and by the operator command
`bio commons frontier rebuild`. Reads never refresh it: an item recorded with
`bio work frontier` and not yet published appears after the next publication or
rebuild.

Clustering of "the same experiment proposed by several questions" is exact-term
overlap (normalized token sets, Jaccard), shown as a suggestion with its shared
terms; a person's confirmation is an attribution event, never a merge. The
wishlist groups exact "missing measurement" statements by normalized text with
no synonym merging.
"""
import json
import re
import sqlite3
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


# ---- Scouting deliverables (V5): datasets inspected for an item, eligible or rejected with a reason ----------
#
# A scouting agent records each dataset it inspected for a frontier item, in its own workspace, as a
# `frontier_item_dataset` work event (`bio work frontier-dataset`), or lists them in one fenced ```datasets JSON
# block in its scouting answer. Either way an entry is {item, accession, inspected: true, eligible, reason,
# receipt}: `item` is a frontier_item/retrieval_gap event of the question (own workspace) or a board frontier
# item id (`frontier_…`, form-checked only, as a workspace cannot see the board); `receipt` is a receipt blob,
# artifact or locator in the recording workspace. Only inspected datasets are deliverables: a candidate nobody
# opened is a watcher query or a gap, not a scouting result. The projection indexes them per item.

DATASET_EVENT = "frontier_item_dataset"
DATASET_FIELDS = {"item", "accession", "inspected", "eligible", "reason", "receipt", "question"}
FRONTIER_ID = re.compile(r"frontier_[0-9a-f]{32}")
DATASETS_FENCE = re.compile(r"^ {0,3}```datasets[ \t]*\r?\n(.*?)\r?\n {0,3}```[ \t]*$", re.MULTILINE | re.DOTALL)
YES, NO = (True, "yes", "true"), (False, "no", "false")


def _flag(value, field):
    if isinstance(value, str):
        value = value.strip().casefold()
    if value in YES:
        return True
    if value in NO:
        return False
    raise DawError("invalid_frontier_dataset", f"{field} is yes or no")


def validate_dataset(ws, payload, question=None):
    """One inspected dataset for a frontier item. With `question` (a work event), a local item must be an event
    of that question; without it (an answer block), the item's own question is used."""
    if not isinstance(payload, dict):
        raise DawError("invalid_frontier_dataset", "use a JSON object")
    unknown = set(payload) - DATASET_FIELDS
    if unknown:
        raise DawError("invalid_frontier_dataset", f"unknown fields {', '.join(sorted(unknown))}")
    if question and payload.get("question", question) != question:
        raise DawError("frontier_question_mismatch")
    item = payload.get("item")
    if not isinstance(item, str) or not item:
        raise DawError("invalid_frontier_dataset", "item names a frontier item")
    if not FRONTIER_ID.fullmatch(item):
        target = ws.one("SELECT * FROM work_event WHERE id=?", (item,))
        if not target or target["kind"] not in ("frontier_item", "retrieval_gap") \
                or (question and target["question_id"] != question):
            raise DawError("invalid_frontier_dataset_target",
                           "name a frontier_item or retrieval_gap event of this question, or a board frontier_ id")
        question = target["question_id"]
    if not _flag(payload.get("inspected"), "inspected"):
        raise DawError("frontier_dataset_not_inspected",
                       "record only datasets you inspected; record a candidate as a watcher query or a gap instead")
    receipt = payload.get("receipt")
    if receipt is None:
        raise DawError("invalid_frontier_dataset", "receipt names the inspection receipt (receipt, artifact or locator)")
    receipt = check_workspace_pointer(ws, receipt)
    if receipt["kind"] not in ("receipt", "artifact", "locator"):
        raise DawError("invalid_frontier_dataset", "receipt is a receipt blob, an artifact or a locator")
    return {"question": question, "item": item, "accession": _text(payload, "accession", 300, required=True),
            "inspected": True, "eligible": _flag(payload.get("eligible"), "eligible"),
            "reason": _text(payload, "reason", 2000, required=True), "receipt": receipt}


def record_dataset(ws, question, *, item, accession, eligible, reason, receipt, inspected=True):
    """Record one inspected dataset for an item (scouting deliverable). Caller holds the workspace writer lock."""
    from daw.work import record_event
    return record_event(ws, question, DATASET_EVENT, {"item": item, "accession": accession, "inspected": inspected,
                                                      "eligible": eligible, "reason": reason, "receipt": receipt})


def dataset_block(text):
    """(entries, problems) from the one fenced ```datasets block of a scouting answer; ([], []) without one."""
    blocks = DATASETS_FENCE.findall(text or "")
    if not blocks:
        return [], []
    if len(blocks) > 1:
        return [], [f"{len(blocks)} ```datasets blocks; write exactly one"]
    try:
        value = json.loads(blocks[0])
    except ValueError as error:
        return [], [f"invalid JSON: {error}"]
    if isinstance(value, dict) and "datasets" in value:
        value = value["datasets"]
    if not isinstance(value, list) or len(value) > 500:
        return [], ["the block holds a JSON list of at most 500 datasets"]
    return value, []


def check_dataset_block(ws, text):
    """(valid entries, problems) of a scouting answer's block, resolved against the answering agent's workspace."""
    entries, problems = dataset_block(text)
    valid = []
    for n, entry in enumerate(entries):
        try:
            valid.append(validate_dataset(ws, entry))
        except DawError as error:
            problems.append(f"dataset {n}: {error.reason}" + (f" ({error.detail})" if error.detail else ""))
    return valid, problems


def scouting_answers(owner):
    """{author: [(post, created, body)]} of answers to scouting requests (the fenced block's source)."""
    found = {}
    for row in owner.rows("SELECT r.answer,p.author,p.created,p.body_blob FROM request r JOIN post p ON p.id=r.answer "
                          "WHERE r.task_type='scouting' AND r.answer IS NOT NULL ORDER BY p.seq"):
        try:
            body = read_json(owner.library.blob_path(row["body_blob"])).get("body") or ""
        except (DawError, OSError, ValueError):
            continue
        found.setdefault(row["author"], []).append((row["answer"], row["created"], body))
    return found


def _dataset_entries(agent, ws, owners, answers):
    """(board item id, entry) pairs recorded by one participant: work events and scouting-answer blocks."""
    out = []
    for event in _events(ws, (DATASET_EVENT,)):
        try:
            payload = read_json(ws.blob_path(event["body_blob"]))
        except (DawError, OSError, ValueError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("item"), str) \
                or not isinstance(payload.get("eligible"), bool) or payload.get("inspected") is not True:
            continue
        out.append((payload, {"source": "work_event", "event": event["id"], "question": event["question_id"],
                              "created": event["created"]}))
    for post, created, body in answers.get(agent["id"], []):
        for entry in check_dataset_block(ws, body)[0]:
            out.append((entry, {"source": "answer_block", "post": post, "question": entry["question"],
                                "created": created}))
    pairs = []
    for payload, origin in out:
        item = payload["item"]
        if not FRONTIER_ID.fullmatch(item):
            owner = owners.get((origin["question"] if origin["source"] == "work_event" else payload.get("question"), item))
            if not owner:
                continue
            item = item_id(owner, item)
        pairs.append((item, {"accession": payload.get("accession"), "eligible": payload["eligible"],
                             "reason": payload.get("reason"), "receipt": payload.get("receipt"),
                             "recorded_by": agent["id"], **origin}))
    return pairs


def datasets_summary(datasets):
    shown = [d for d in datasets or [] if not d.get("hidden")]
    return {"inspected": len(shown), "eligible": sum(1 for d in shown if d.get("eligible")),
            "rejected": sum(1 for d in shown if d.get("eligible") is False),
            "withheld": sum(1 for d in datasets or [] if d.get("hidden"))}


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


SOURCE_EVENTS = ("frontier_item", "frontier_item_status", "retrieval_gap", "retrieval_gap_withdrawal", DATASET_EVENT)


def frontier_key(owner):
    """What the projection is a function of: the last board event of a kind that owns frontier state, the
    participants with checkouts, and each workspace's frontier-relevant work events (count and latest time).
    Stored in projection_state by every rebuild; a read compares it to say whether the projection is behind."""
    marks = ",".join("?" for _ in KEY_EVENTS)
    sequence = owner.one(f"SELECT coalesce(max(seq),0) AS n FROM event WHERE kind IN ({marks})", KEY_EVENTS)["n"]
    kinds = ",".join("?" for _ in SOURCE_EVENTS)
    counts = []
    for agent, ws in workspaces(owner):
        row = ws.one(f"SELECT count(*) AS n,coalesce(max(created),'') AS m FROM work_event WHERE kind IN ({kinds})",
                     SOURCE_EVENTS)
        counts.append([agent["id"], row["n"], row["m"]])
    return f"{sequence}:{digest(counts)[:32]}"


def stored_key(owner, name="frontier"):
    try:
        row = owner.one("SELECT key FROM projection_state WHERE name=?", (name,))
    except Exception:  # an archive opened before the board gained the bookkeeping table
        return None
    return row["key"] if row else None


# Board events that own frontier state. The projection is a pure function of these events and the
# participants' workspace records, so dropping the table and rebuilding reproduces it byte for byte.
BOARD_EVENTS = ("promotion_created", "watcher_added", "watcher_disabled", "watcher_ran")
# The projection key also covers completed deliveries: a scouting answer's ```datasets block is a source (V5).
KEY_EVENTS = BOARD_EVENTS + ("delivery_completed",)
COLUMNS = ("question", "author", "workspace", "kind", "text", "status", "blocked_by", "watcher_query",
           "pointers", "source", "created", "updated", "promoted_to")


def _empty_state():
    return {"promotions": [], "watchers": {}, "candidates": []}


def _count(value):
    if isinstance(value, list):
        return len(value)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def board_state(owner):
    """Board-owned state per frontier item, derived from immutable board events in sequence order:
    promotions (`promotion_created` with a frontier_item source), attached and disabled watchers
    (`watcher_added`, `watcher_disabled`) and watcher runs that moved an item to candidate evidence
    (`watcher_ran`). Works on a Community or a read-only Archive."""
    state = {}
    marks = ",".join("?" for _ in BOARD_EVENTS)
    for row in owner.rows(f"SELECT seq,kind,body,created FROM event WHERE kind IN ({marks}) ORDER BY seq", BOARD_EVENTS):
        try:
            body = json.loads(row["body"])
        except ValueError:
            continue
        if not isinstance(body, dict):
            continue
        kind = row["kind"]
        if kind == "promotion_created":
            source = body.get("source") if isinstance(body.get("source"), dict) else {}
            if source.get("kind") == "frontier_item" and isinstance(source.get("id"), str):
                state.setdefault(source["id"], _empty_state())["promotions"].append(
                    {"request": body.get("request"), "actor": body.get("actor"), "event_seq": row["seq"],
                     "created": row["created"]})
            continue
        if not isinstance(body.get("item"), str) or not isinstance(body.get("watcher"), str):
            continue
        entry = state.setdefault(body["item"], _empty_state())
        if kind == "watcher_added":
            query = body.get("query") if isinstance(body.get("query"), dict) else {"query": body.get("query")}
            entry["watchers"][body["watcher"]] = {"watcher": body["watcher"], "provider": body.get("provider"),
                                                  "query": query, "enabled": True, "event_seq": row["seq"]}
        elif kind == "watcher_disabled":
            if body["watcher"] in entry["watchers"]:
                entry["watchers"][body["watcher"]]["enabled"] = False
            # The query shown after disabling, as recorded at the time ("watcher <id>", "author" or none).
            if "watcher_query" in body:
                entry["shown_after_disable"] = {"query": body["watcher_query"], "event_seq": row["seq"],
                                                "source": body.get("watcher_query_source")}
        else:  # watcher_ran
            new = _count(body.get("new"))
            # `status_set` ("candidate_evidence", by `status_source` "watcher") records that this run moved an open
            # item to candidate evidence; older events say `status_changed`; a run recorded with neither counts
            # when it found new accessions.
            if "status_set" in body:
                changed = body["status_set"] == "candidate_evidence"
            elif isinstance(body.get("status_changed"), bool):
                changed = body["status_changed"]
            else:
                changed = new > 0
            if changed:
                accessions = body.get("new_accessions")
                entry["candidates"].append({"source": "watcher", "watcher": body["watcher"], "run": body.get("run"),
                                            "new": new, "accessions": accessions if isinstance(accessions, list) else None,
                                            "event_seq": row["seq"], "created": row["created"]})
    return state


def _status(agent_item, owned, datasets=()):
    """(status, updated, candidate). An agent's closed/withdrawn status always wins. Then scouting (V5): inspected
    datasets recorded at or after the agent's latest status and the latest promotion settle that promotion: any
    eligible dataset makes the item candidate evidence (source `scouting`, so the analysis can be promoted from
    it); none eligible returns the item to the agent's own status. Then a person's promotion; then a watcher's
    candidate evidence recorded at or after the agent's latest status; otherwise the agent's own status (an agent
    may record candidate_evidence itself, attributed to the author). Without datasets nothing here changes."""
    status, when = agent_item["status"], agent_item["status_time"]
    if status in ("closed", "withdrawn"):
        return status, when, None
    promoted = bool(owned["promotions"])
    if datasets:
        since = max([when] + [p["created"] for p in owned["promotions"][-1:]])
        settled = [d for d in datasets if d["created"] >= since]
        if settled:
            eligible = [d for d in settled if d["eligible"]]
            latest = max(d["created"] for d in settled)
            if eligible:
                return "candidate_evidence", latest, {"source": "scouting", "inspected": len(settled),
                                                      "eligible": len(eligible),
                                                      "records": [d.get("event") or d.get("post") for d in eligible]}
            promoted = False  # scouting found nothing eligible: the promotion is settled, the item is the agent's again
    if promoted:  # with scouting records, the promotion after them (an analysis promoted from candidate evidence)
        return "promoted", owned["promotions"][-1 if datasets else 0]["created"], None
    latest = owned["candidates"][-1] if owned["candidates"] else None
    if latest and when <= latest["created"]:
        return "candidate_evidence", latest["created"], {k: v for k, v in latest.items() if k != "created"}
    if status == "candidate_evidence":
        return status, when, {"source": "author", "status_event": agent_item.get("status_event")}
    return status, when, None


def _watcher_query(item, owned):
    """The latest enabled board watcher's query masks the author's. After the last one is disabled, the query the
    `watcher_disabled` event recorded as shown (the author's own, unmasked) is used; boards recorded before that
    field fall back to the author's query from the workspace event."""
    enabled = [w for w in owned["watchers"].values() if w["enabled"]]
    if enabled:
        latest = max(enabled, key=lambda w: w["event_seq"])
        return canonical({"watcher": latest["watcher"], "provider": latest["provider"], **latest["query"]}).decode()
    shown = owned.get("shown_after_disable")
    if shown and shown["source"] != "watcher" and not str(shown["source"] or "").startswith("watcher "):
        query = shown["query"]
        return None if query is None else query if isinstance(query, str) else canonical(query).decode()
    query = item["watcher_query"]
    return None if query is None else query if isinstance(query, str) else canonical(query).decode()


def _drop_documents(library, identities):
    """Remove the search documents of deleted rows (a disposable projection in the library catalog)."""
    keys = ["frontier:" + i for i in identities]
    if not keys:
        return
    marks = ",".join("?" for _ in keys)
    with library.db:
        library.db.execute(f"DELETE FROM search_embedding WHERE document_id IN ({marks})", keys)
        library.db.execute(f"DELETE FROM search_fts WHERE id IN ({marks})", keys)
        library.db.execute(f"DELETE FROM search_document WHERE id IN ({marks})", keys)


def project(board):
    """The projection rows {id: values} computed from workspaces and board events, plus scan counts."""
    owners, computed, inherited = {}, [], 0
    answers = scouting_answers(board)
    found = {}
    for agent, ws in workspaces(board):
        for item in workspace_items(ws):
            if owners.setdefault((item["question"], item["event"]), agent["id"]) != agent["id"]:
                inherited += 1
                continue
            computed.append((agent, item))
        for identity, entry in _dataset_entries(agent, ws, owners, answers):
            # A fork's copy of an inherited event counts once, attributed to the original recorder (oldest first).
            found.setdefault(identity, {}).setdefault((entry.get("event") or entry.get("post"), entry["accession"]), entry)
    datasets = {i: sorted(entries.values(), key=lambda d: (d["created"], d.get("event") or d.get("post") or "",
                                                           d.get("accession") or ""))
                for i, entries in found.items()}
    state = board_state(board)
    rows = {}
    for agent, item in computed:
        identity = item_id(agent["id"], item["event"])
        owned = state.get(identity) or _empty_state()
        status, when, candidate = _status(item, owned, datasets.get(identity, ()))
        promotion = owned["promotions"][-1] if owned["promotions"] else None
        source = {"event": item["event"], "event_kind": item["event_kind"], "body_blob": item["body_blob"],
                  "missing_measurement": item["missing_measurement"], "key": item["key"], "post": item["post"],
                  "status_event": item.get("status_event"), "status_reason": item["status_reason"],
                  "agent_status": item["status"], "detail": item["detail"],
                  "candidate_source": candidate["source"] if candidate else None, "candidate": candidate,
                  "promotion": {k: promotion[k] for k in ("request", "actor", "event_seq")} if promotion else None,
                  "watchers": sorted(owned["watchers"])}
        if datasets.get(identity):  # only when recorded, so boards without scouting keep their rows byte for byte
            source["datasets"] = datasets[identity]
        rows[identity] = {"question": item["question"], "author": agent["id"],
                          "workspace": str(Path(agent["trial"]) / "workspace"), "kind": item["kind"],
                          "text": item["text"], "status": status, "blocked_by": item["blocked_by"],
                          "watcher_query": _watcher_query(item, owned), "pointers": canonical(item["pointers"]).decode(),
                          "source": canonical(source).decode(), "created": item["created"], "updated": when,
                          "promoted_to": promotion["request"] if promotion else None}
    return rows, {"items": len(computed), "inherited_skipped": inherited}


def reindex(board, *, reason=None):
    """Bring the frontier projection up to date. The caller holds `board.writer()` and `board.library.writer()`
    (the write paths: publication with frontier items or a notebook, promotion, watcher events)."""
    rows, counts = project(board)
    existing = {r["id"]: r for r in board.rows("SELECT * FROM frontier_item")}
    inserted, updated, changed = 0, 0, []
    orphaned = sorted(set(existing) - set(rows))
    with board.db:
        for identity, values in rows.items():
            old = existing.get(identity)
            if old and all(old[c] == values[c] for c in COLUMNS):
                continue
            if old:
                board.db.execute("UPDATE frontier_item SET " + ",".join(f"{c}=?" for c in COLUMNS) + " WHERE id=?",
                                 [values[c] for c in COLUMNS] + [identity])
                updated += 1
            else:
                board.db.execute("INSERT INTO frontier_item(id," + ",".join(COLUMNS) + ") VALUES(?,"
                                 + ",".join("?" for _ in COLUMNS) + ")", [identity] + [values[c] for c in COLUMNS])
                inserted += 1
            changed.append({"id": identity, **values})
        if orphaned:
            # Rows no workspace record supports (a removed checkout, or a row written outside this function).
            board.db.execute(f"DELETE FROM frontier_item WHERE id IN ({','.join('?' for _ in orphaned)})", orphaned)
    for row in changed:
        blob = board.library.put_json({"format": "daw.frontier_item/1", **row})
        index_document(board.library, key="frontier:" + row["id"], family="frontier", subject=row["id"],
                       record_id=row["id"], title=row["text"][:200], summary=row["text"][:2000], body_blob=blob,
                       detail={"kind": row["kind"], "status": row["status"], "blocked_by": row["blocked_by"],
                               "question": row["question"], "author": row["author"],
                               "missing_measurement": json.loads(row["source"]).get("missing_measurement")},
                       provider="community", level=3)
    _drop_documents(board.library, orphaned)
    summary = {**counts, "inserted": inserted, "updated": updated, "deleted": len(orphaned), "orphaned": orphaned}
    with board.db:
        if inserted or updated or orphaned:
            board.event("frontier_reindexed", {**{k: v for k, v in summary.items() if k != "orphaned"},
                                               **({"reason": reason} if reason else {})})
        key = frontier_key(board)
        board.db.execute("INSERT INTO projection_state(name,key,updated) VALUES('frontier',?,?) "
                         "ON CONFLICT(name) DO UPDATE SET key=excluded.key,updated=excluded.updated", (key, now()))
    return {**summary, "key": key}


def rebuild_frontier(board, *, reason=None):
    """Rebuild the frontier projection from every participant workspace (read-only scan) and the board's own
    events (promotions, watchers). Idempotent; deletes rows no record supports. A fork's inherited items (same
    question and event as an older participant) stay attributed to the original author; the fork's status
    events on inherited items are not applied. Operators run it as `bio commons frontier rebuild`."""
    with board.writer(), board.library.writer():
        summary = reindex(board, reason=reason)
        # Shared experiments (V5) read member questions from confirmation events; refreshed alongside.
        from daw.commons.planning import rebuild_experiments
        summary["shared_experiments"] = rebuild_experiments(board, reason=reason)
        return summary


def reindex_after_publish(board, post):
    """Write-path refresh after a publication that carried frontier items or a notebook sync. The post is
    already immutable, so a failed refresh is recorded as an event rather than raised; the operator can run
    `bio commons frontier rebuild`."""
    try:
        return rebuild_frontier(board, reason=f"published {post}")
    except (DawError, sqlite3.Error, OSError, ValueError) as error:
        with board.writer(), board.db:
            board.event("frontier_reindex_failed", {"post": post, "error": getattr(error, "reason", type(error).__name__)})
        return None


def is_current(view):
    """True when the stored projection equals what a rebuild would write now (computed read-only; a read never
    refreshes it). False means a workspace recorded items that no publication or rebuild has indexed yet."""
    rows, _ = project(view)
    existing = {r["id"]: r for r in view.rows("SELECT * FROM frontier_item")}
    return set(rows) == set(existing) and all(existing[i][c] == v[c] for i, v in rows.items() for c in COLUMNS)


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
    rows = board.rows(f"SELECT id,question,kind,text FROM frontier_item WHERE id IN ({','.join('?' for _ in items)})",
                      items)
    if len(rows) != len(items):
        raise DawError("unknown_frontier_item", ", ".join(sorted(set(items) - {r["id"] for r in rows})))
    if len({r["question"] for r in rows}) < 2:
        raise DawError("invalid_cluster", "a cluster spans at least two questions")
    if not isinstance(note, str) or len(note) > 2000:
        raise DawError("invalid_cluster", "note is text up to 2000 characters")
    shared = sorted(frozenset.intersection(*(tokens(r["text"]) for r in rows)))
    kinds = {r["kind"] for r in rows}
    # V5: the event names the member questions (and the common kind), so the shared experiment it creates is
    # rebuildable from the event alone.
    body = {"items": items, "participant": participant["id"], "note": note.strip(), "shared_terms": shared,
            "questions": sorted({r["question"] for r in rows}), "kind": kinds.pop() if len(kinds) == 1 else None}
    from daw.commons.planning import experiment_id, rebuild_experiments
    with board.writer():
        with board.db:
            board.event("frontier_cluster_confirmed", body)
            seq = board.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        # The confirmation merges nothing; it creates (or adds a confirmation to) a shared experiment record.
        rebuild_experiments(board, reason=f"frontier_cluster_confirmed {seq}")
    return {"seq": seq, **body, "shared_experiment": experiment_id(items),
            "note_on_meaning": "attribution only; items are not merged or re-scoped"}


def describe_item(row):
    source = json.loads(row["source"])
    query = row["watcher_query"]
    try:
        query = json.loads(query) if query and query.startswith("{") else query
    except ValueError:
        pass
    return {**row, "pointers": json.loads(row["pointers"]), "source": source, "watcher_query": query,
            "missing_measurement": source.get("missing_measurement"), "status_reason": source.get("status_reason"),
            "candidate_source": source.get("candidate_source"), "detail": source.get("detail") or {},
            "datasets": source.get("datasets") or [], "datasets_summary": datasets_summary(source.get("datasets")),
            "content_is_untrusted_data": True}


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


def _is_post_pointer(pointer):
    kind, identity = pointer.get("kind"), pointer.get("id")
    return isinstance(identity, str) and (kind == "post" or (kind == "locator" and bool(POST_ID.fullmatch(identity))))


def candidate_evidence_records(owner, ids):
    """Watcher runs that moved each item to candidate_evidence, from their `watcher_ran` events (body
    `status_set: "candidate_evidence"`, `status_source: "watcher"`; older events say `status_changed`)."""
    found = {i: [] for i in ids}
    if not ids:
        return found
    for row in owner.rows("SELECT seq,body,created FROM event WHERE kind='watcher_ran' ORDER BY seq"):
        body = json.loads(row["body"])
        if body.get("item") in found and (body.get("status_set") == "candidate_evidence" or body.get("status_changed")):
            found[body["item"]].append({"by": "watcher", "watcher": body.get("watcher"), "run": body.get("run"),
                                        "post": body.get("post"), "event_seq": row["seq"], "created": row["created"]})
    return found


def annotate(owner, items):
    """Read-time facts about described items, all from records (spec v2 C9):

    - `candidate_evidence`: for an item in that status, whether a watcher set it (its `watcher_ran` event),
      the item's author did (an agent `frontier_item_status` event), or both; "unrecorded" when neither.
    - `present` on every post pointer, and `post_present` for the item's own post: whether that post exists
      on this board. A workspace can check only a post id's form when the agent records the item.
    """
    for item in items:
        item["candidate_evidence"] = None
    candidates = [i for i in items if i.get("status") == "candidate_evidence"]
    by_watcher = candidate_evidence_records(owner, [i["id"] for i in candidates])
    for item in candidates:
        source = item["source"] if isinstance(item.get("source"), dict) else {}
        records = list(by_watcher[item["id"]])
        if source.get("agent_status") == "candidate_evidence":
            records.insert(0, {"by": "author", "event": source.get("status_event"), "reason": source.get("status_reason")})
        if source.get("candidate_source") == "scouting":  # V5: eligible datasets a scouting task inspected
            candidate = source.get("candidate") or {}
            records.append({"by": "scouting", "eligible": candidate.get("eligible"), "inspected": candidate.get("inspected"),
                            "records": candidate.get("records")})
        by = sorted({r["by"] for r in records})
        item["candidate_evidence"] = {"set_by": " and ".join(by) if by else "unrecorded", "records": records}
    posts = {p["id"] for i in items for p in i.get("pointers") or [] if isinstance(p, dict) and _is_post_pointer(p)}
    posts |= {i["source"]["post"] for i in items
              if isinstance(i.get("source"), dict) and isinstance(i["source"].get("post"), str)}
    posts = sorted(posts)
    present = {r["id"] for r in owner.rows(f"SELECT id FROM post WHERE id IN ({','.join('?' for _ in posts)})",
                                           posts)} if posts else set()
    for item in items:
        item["pointers"] = [{**p, "present": p["id"] in present} if isinstance(p, dict) and _is_post_pointer(p) else p
                            for p in item.get("pointers") or []]
        post = item["source"].get("post") if isinstance(item.get("source"), dict) else None
        item["post_present"] = (post in present) if isinstance(post, str) else None
    # A dataset listed in a scouting answer hidden by moderation is that post's content (spec v2 C2).
    from daw.commons.moderation import Visibility
    vis = Visibility.of(owner)
    for item in items:
        if item.get("datasets"):
            item["datasets"] = [{"hidden": True, "post": d["post"], "reason": vis.reason(d["post"])}
                                if d.get("post") and vis.withheld(d["post"]) else d for d in item["datasets"]]
            item["datasets_summary"] = datasets_summary(item["datasets"])
    return items


def author_watcher_query(owner, row):
    """The watcher query the item's author recorded in their own work event, in stored form, or None.
    Opens the author's workspace read-only."""
    try:
        source = json.loads(row["source"])
    except (TypeError, ValueError):
        return None
    agent = owner.one("SELECT id,trial FROM agent WHERE id=?", (row["author"],))
    if not isinstance(source, dict) or not isinstance(source.get("body_blob"), str) or not agent or not agent["trial"]:
        return None
    try:
        ws = ReadOnlyWorkspace(_workspace_path(Path(owner.root), agent))
    except (DawError, OSError, sqlite3.Error):
        return None
    try:
        payload = read_json(ws.blob_path(source["body_blob"]))
    except (DawError, OSError, ValueError):
        return None
    finally:
        ws.close()
    query = payload.get("watcher_query") if isinstance(payload, dict) else None
    if isinstance(query, str):
        return query.strip() or None
    return canonical(query).decode() if isinstance(query, dict) and query else None


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
    annotate(owner, rows)
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
