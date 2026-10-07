"""Human participation (M2.4–M2.7): posts, uploads, comments at anchors, marks, promotions, commissions.

Every function takes the board, the acting participant's identity and the
operation's fields; it checks `permissions.require` itself (never only in the HTTP
layer), holds `board.writer()` (plus `board.library.writer()` when storing bytes)
and records one board event. Posts go through `Community._post`, so human content
is validated, stored and indexed exactly like agent content and is equally
untrusted to every reader.

- A comment is a reply post of kind "comment". Its anchor is a locator into
  immutable bytes (blob hash plus offset/length, a row key or a map node id) and
  is validated against those bytes, so it survives re-rendering. Asking the author
  turns the comment post itself into a typed request (task type `question`).
- A person's ask (`ask`, or a comment with ask_author) is a typed request of type
  `question` (daw.commons.tasks.QUESTION) with a budget, checked against the asker's
  allowance exactly like a promotion; the runtime delivers it only while that
  allowance permits and labels its text as attributed board content from a human
  participant, not an instruction override. Agents' own peer questions stay untyped.
- A mark is attribution: an immutable row plus a body blob. It never changes a
  status the platform computes.
- Promotion and commission are the only paths that schedule new work. They create
  a request with a task type, budget and deadline, spent against the person's
  operator-set allowance.
- Rate limits are checked inside the board writer lock, so concurrent requests
  cannot both pass the same remaining allowance of writes.
- A human post that supersedes the person's own earlier post notifies the readers
  who fetched the superseded post's evidence (`claims.notify_affected`), exactly as
  `Community.publish` does (Flow B).
- Uploads are library objects with a receipt. They are evidence of kind upload:
  never registered as derivations, never executed, never served as HTML.
"""
import json
import re
import tomllib
import uuid
from datetime import UTC, datetime

from daw.commons.archive import Archive
from daw.commons.claims import notify_affected
from daw.commons.moderation import check_rate, limits
from daw.commons.permissions import require
from daw.commons.replication import refuse_producer
from daw.commons.tasks import (BUDGET_FIELDS, BUDGETED_TYPES, COMMISSION_TYPES, DEFAULT_ASK_BUDGET, QUESTION,
                               check_deadline, check_task_type, normalize_budget)
from daw.profiles import verify_object
from daw.util import DawError, canonical, now, read_json

COMMENT_TARGETS = ("post", "question", "artifact", "node", "claim", "run")
ANCHOR_KINDS = ("paragraph", "line", "row", "node")
MARK_TARGETS = ("post", "claim", "artifact")
MARK_KINDS = ("checked_source", "reproduced", "disputed")
PROMOTION_SOURCES = ("frontier_item", "post", "claim")
POINTER_KINDS = ("post", "artifact", "receipt", "locator", "accession", "upload", "claim", "run", "question")
SUBJECT_KINDS = ("post", "claim", "artifact", "question", "run", "frontier_item")
OPEN_FRONTIER = ("open", "candidate_evidence")
MAX_BODY = 20000
MAX_QUOTE = 5000
MAX_ANCHOR_BLOB = 64 * 1024 * 1024
MEDIA_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,63}$")
QUESTION_ID = re.compile(r"^q_[0-9a-f]{16}$")
UPLOAD_NOTE = "Uploaded bytes are evidence of kind upload: never executed, rendered as HTML or registered as a derivation."


def _actor(board, actor, action):
    return require(board, board.agent(actor), action)


def _text(value, reason, limit=MAX_BODY):
    value = (value or "").strip()
    if not value or len(value) > limit:
        raise DawError(reason, f"required, at most {limit} characters")
    return value


# --- posts and uploads (M2.4) -------------------------------------------------------------------

def _uploads(board, upload_ids):
    items = []
    for identity in dict.fromkeys(upload_ids or ()):
        row = board.one("SELECT * FROM upload WHERE id=?", (identity,))
        if not row:
            raise DawError("unknown_upload", identity)
        items.append({k: row[k] for k in ("id", "blob", "name", "media_type", "size", "receipt_blob")})
    return items


def post(board, actor, title, body, *, parent=None, supersedes=None, upload_ids=()):
    """Publish a human post (or reply) through the board's own post path; uploads attach as evidence."""
    person = _actor(board, actor, "reply" if parent else "post")
    evidence = {}
    uploads = _uploads(board, upload_ids)
    if uploads:
        evidence["upload"] = uploads
    title, body = _text(title, "empty_post", 300), _text(body, "empty_post")
    with board.writer(), board.library.writer():
        check_rate(board, person, "posts_per_hour")
        identity = board._post(person["id"], title, body, parent=parent, supersedes=supersedes, evidence=evidence)
        board._settle_request(identity, parent)
    if supersedes:
        # Flow B, exactly as Community.publish: readers who fetched the superseded post's evidence get a notice.
        notify_affected(board, identity)
    return board.show(identity)


def clean_filename(name):
    """Basename only, conservative characters, no leading dots; never trusted for paths or rendering."""
    name = re.split(r"[\\/]", str(name or ""))[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name[:200] or "upload"


def upload(board, actor, filename, data, media_type="application/octet-stream"):
    """Store bytes as a library object with a receipt; returns the immutable upload row."""
    person = _actor(board, actor, "upload")
    if not isinstance(data, bytes | bytearray) or not data:
        raise DawError("empty_upload")
    limit = limits(board.root)["upload_bytes"]
    if len(data) > limit:
        raise DawError("upload_too_large", f"limit is {limit} bytes")
    media_type = (media_type or "application/octet-stream").split(";")[0].strip().lower()
    if not MEDIA_TYPE.match(media_type):
        raise DawError("invalid_media_type", media_type[:80])
    name = clean_filename(filename)
    identity = "upload_" + uuid.uuid4().hex
    with board.writer(), board.library.writer():
        check_rate(board, person, "uploads_per_hour")
        blob = board.library.put_bytes(bytes(data), "upload")
        receipt = {"kind": "upload_receipt", "upload": identity, "uploader": person["id"], "uploader_kind": person["kind"],
                   "filename": name, "declared_media_type": media_type, "size": len(data), "sha256": blob,
                   "received": now(), "note": UPLOAD_NOTE}
        receipt_blob = board.library.put_json(receipt)
        with board.db:
            board.db.execute("INSERT INTO upload(id,blob,name,uploader,media_type,size,receipt_blob,created) "
                             "VALUES(?,?,?,?,?,?,?,?)",
                             (identity, blob, name, person["id"], media_type, len(data), receipt_blob, receipt["received"]))
            board.event("upload_received", {"upload": identity, "uploader": person["id"], "blob": blob,
                                            "size": len(data), "receipt_blob": receipt_blob})
    return board.one("SELECT * FROM upload WHERE id=?", (identity,))


# --- comments at anchors (M2.5) -----------------------------------------------------------------

def _naming_posts(board, predicate):
    named = []
    for row in board.rows("SELECT body FROM event WHERE kind='published' ORDER BY seq"):
        body = json.loads(row["body"])
        if predicate(body.get("evidence") or {}):
            named.append(body["post"])
    return named


def comment_target(evidence):
    """(kind, id) of a comment's target from its post evidence; questions are identified as '<owner>:<qid>'."""
    target = evidence.get("target") if isinstance(evidence, dict) else None
    if not isinstance(target, dict):
        return None, None
    kind, identity = target.get("kind"), target.get("id")
    if kind == "question" and isinstance(identity, str) and ":" not in identity and target.get("author"):
        identity = f"{target['author']}:{identity}"
    return kind, identity


def question_owner(view, identity):
    """(owner, question) for 'q_…', 'owner/q_…' or 'owner:q_…' (the question page's id). A bare id resolves to the
    earliest participant holding it (forks copy their parent's questions, and the original author precedes its forks)."""
    owner, _, question = identity.replace(":", "/").rpartition("/")
    if not QUESTION_ID.match(question):
        raise DawError("unknown_question", identity)
    candidates = [view.participant(owner)] if owner else view.rows(
        "SELECT * FROM agent WHERE trial IS NOT NULL ORDER BY created,id")
    for agent in candidates:
        workspace = view.workspace(agent["id"])
        if workspace and workspace.one("SELECT id FROM question WHERE id=?", (question,)):
            return agent["id"], question, workspace
    raise DawError("unknown_question", identity)


def _resolve(board, view, kind, identity):
    """Target record: owner (participant to ask), parent post, and the blobs an anchor may point into."""
    if kind not in COMMENT_TARGETS:
        raise DawError("invalid_comment_target", f"use one of {', '.join(COMMENT_TARGETS)}")
    identity = (identity or "").strip()
    if kind == "post":
        shown = board.show(identity)
        return {"id": identity, "owner": shown["author"], "parent": identity,
                "blobs": {shown["body_blob"]: ("post", shown["content"]["body"])}}
    if kind == "question":
        owner, question, workspace = question_owner(view, identity)
        blobs = {}
        for snap in workspace.rows("SELECT body_blob FROM work_snapshot WHERE question_id=?", (question,)):
            for sha in read_json(workspace.blob_path(snap["body_blob"])).get("files", {}).values():
                blobs[sha] = ("workspace", workspace)
        named = _naming_posts(board, lambda e: (e.get("notebook") or {}).get("question") == question)
        authored = [p for p in named if board.one("SELECT author FROM post WHERE id=?", (p,))["author"] == owner]
        return {"id": question, "owner": owner, "parent": authored[-1] if authored else None, "blobs": blobs}
    if kind == "artifact":
        sources = [view.library] + [w for w in (view.workspace(a["id"]) for a in view.rows(
            "SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY created,id")) if w]
        rows = [(ws, ws.one("SELECT * FROM artifact WHERE id=?", (identity,))) for ws in sources]
        rows = [(ws, row) for ws, row in rows if row]
        if not rows:
            raise DawError("unknown_artifact", identity)
        named = _naming_posts(board, lambda e: identity in e.get("artifacts", []))
        owner = board.one("SELECT author FROM post WHERE id=?", (named[0],))["author"] if named else None
        if owner is None:
            for agent in view.rows("SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY created,id"):
                workspace = view.workspace(agent["id"])
                if workspace and workspace.one("SELECT 1 FROM question_artifact WHERE artifact_id=? AND "
                                               "relationship='produced'", (identity,)):
                    owner = agent["id"]
                    break
        return {"id": identity, "owner": owner, "parent": named[-1] if named else None,
                "blobs": {rows[0][1]["output_blob"]: ("workspace", rows[0][0])}}
    if kind == "claim":
        row = board.one("SELECT * FROM claim WHERE id=?", (identity,))
        if not row:
            raise DawError("unknown_claim", identity)
        shown = board.show(row["post"])
        return {"id": identity, "owner": row["author"], "parent": row["post"],
                "blobs": {row["claims_blob"]: ("workspace", view.library),
                          shown["body_blob"]: ("post", shown["content"]["body"])}}
    if kind == "run":
        attempt = board.one("SELECT * FROM attempt WHERE id=?", (identity,))
        if not attempt:
            raise DawError("unknown_run", identity)
        request = board.one("SELECT * FROM request WHERE id=?", (attempt["request"],))
        answered = request["answer"] and request["active_run"] == identity
        return {"id": identity, "owner": attempt["target"], "parent": request["answer"] if answered else request["post"],
                "blobs": {}}
    # Map nodes: a recorded identifier (optionally "kind:identifier") resolves to that record; otherwise
    # the node is named only in the comment's evidence.
    if not identity or len(identity) > 300:
        raise DawError("invalid_comment_target", "node id required")
    inner = identity.split(":", 1)[-1]
    for prefix, inner_kind in (("post_", "post"), ("artifact_", "artifact"), ("run_", "run"), ("claim_", "claim")):
        if inner.startswith(prefix):
            try:
                resolved = _resolve(board, view, inner_kind, inner)
            except DawError:
                break
            return {**resolved, "id": identity, "blobs": {}}
    if QUESTION_ID.match(inner.rpartition("/")[2]):
        try:
            return {**_resolve(board, view, "question", inner), "id": identity, "blobs": {}}
        except DawError:
            pass
    return {"id": identity, "owner": None, "parent": None, "blobs": {}}


def _anchored_text(source, sha):
    origin, value = source
    if origin == "post":
        return value
    path = verify_object(value, sha)
    if path.stat().st_size > MAX_ANCHOR_BLOB:
        raise DawError("anchor_blob_too_large", sha)
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as e:
        raise DawError("anchor_blob_not_text", sha) from e


def _span(text, offset, length, quote):
    """Code-point (offset, length) of the anchored span. Browsers count UTF-16 code units; when a quote is
    given and only matches under that reading, the span is converted so stored locators are code points."""
    if isinstance(offset, bool) or isinstance(length, bool) or not isinstance(offset, int) or not isinstance(length, int):
        raise DawError("invalid_anchor", "offset and length must be integers")
    if offset < 0 or length < 1 or length > MAX_QUOTE:
        raise DawError("invalid_anchor", f"offset >= 0 and 1 <= length <= {MAX_QUOTE}")
    if offset + length <= len(text) and (quote is None or text[offset:offset + length] == quote):
        return offset, length
    if quote is not None:
        units = text.encode("utf-16-le")
        if (offset + length) * 2 <= len(units):
            try:
                start = len(units[:offset * 2].decode("utf-16-le"))
                piece = units[offset * 2:(offset + length) * 2].decode("utf-16-le")
            except UnicodeDecodeError:
                piece = None
            if piece == quote:
                return start, len(piece)
        raise DawError("anchor_quote_mismatch", "the quote does not equal the anchored bytes")
    raise DawError("anchor_out_of_range", f"text has {len(text)} characters")


def _row(text, row_key, quote):
    lines = text.splitlines()
    if len(lines) < 2:
        raise DawError("anchor_blob_not_tabular")
    delimiter = "\t" if "\t" in lines[0] else ","
    rows = lines[1:]
    if re.fullmatch(r"#[1-9]\d*", row_key):
        index = int(row_key[1:]) - 1
        if index >= len(rows):
            raise DawError("anchor_row_missing", row_key)
    else:
        matches = [i for i, line in enumerate(rows) if line.split(delimiter, 1)[0] == row_key]
        if not matches:
            raise DawError("anchor_row_missing", row_key)
        if len(matches) > 1:
            raise DawError("anchor_row_ambiguous", "use '#N' (1-based data row) for duplicated first fields")
        index = matches[0]
    if quote is not None and quote != rows[index]:
        raise DawError("anchor_quote_mismatch", "the quote does not equal the anchored row")
    return index + 1, rows[index]


def _anchor(target_kind, target, anchor):
    """Validate an anchor against the target's immutable bytes and return the stored locator."""
    if anchor is None:
        return None
    if not isinstance(anchor, dict):
        raise DawError("invalid_anchor", "object expected")
    unknown = set(anchor) - {"kind", "blob", "offset", "length", "row_key", "node_id", "quote"}
    if unknown:
        raise DawError("invalid_anchor", f"unknown fields {', '.join(sorted(unknown))}")
    kind = anchor.get("kind")
    if kind not in ANCHOR_KINDS:
        raise DawError("invalid_anchor", f"kind must be one of {', '.join(ANCHOR_KINDS)}")
    quote = anchor.get("quote")
    if quote is not None and (not isinstance(quote, str) or not quote or len(quote) > MAX_QUOTE):
        raise DawError("invalid_anchor", "quote must be non-empty text")
    locator = {"target_kind": target_kind, "target_id": target["id"], "kind": kind}
    if kind == "node":
        node = anchor.get("node_id")
        if not isinstance(node, str) or not node.strip() or len(node) > 300:
            raise DawError("invalid_anchor", "node_id required")
        return {**locator, "node_id": node.strip(), **({"quote": quote} if quote else {})}
    sha = anchor.get("blob")
    if sha not in target["blobs"]:
        raise DawError("anchor_blob_not_in_target", f"{sha} is not part of {target_kind} {target['id']}")
    text = _anchored_text(target["blobs"][sha], sha)
    if kind == "row":
        key = anchor.get("row_key")
        if not isinstance(key, str) or not key or len(key) > 300:
            raise DawError("invalid_anchor", "row_key required")
        number, line = _row(text, key, quote)
        return {**locator, "blob": sha, "row_key": key, "row": number, "quote": line[:MAX_QUOTE]}
    offset, length = _span(text, anchor.get("offset"), anchor.get("length"), quote)
    return {**locator, "blob": sha, "offset": offset, "length": length, "line": text.count("\n", 0, offset) + 1,
            "quote": text[offset:offset + length]}


def _addressee(board, owner, person):
    if not owner:
        raise DawError("target_has_no_author", "this target has no participant to ask; comment without ask_author")
    agent = board.agent(owner)
    if agent["id"] == person["id"]:
        raise DawError("cannot_ask_yourself")
    if agent["kind"] == "agent":
        board.trial(agent)
    elif agent["kind"] not in {"human", "operator"}:
        raise DawError("participant_cannot_receive_requests", agent["kind"])
    return agent


def _ask_terms(budget, deadline):
    """A person's ask carries a budget like a promotion (DEFAULT_ASK_BUDGET when none is stated)."""
    budget = normalize_budget(budget) or dict(DEFAULT_ASK_BUDGET)
    return budget, _deadline(deadline)


def _insert_request(board, post, target, task_type=None, budget=None, deadline=None):
    """One pending request row; the caller holds the board writer lock and an open transaction."""
    request = "request_" + uuid.uuid4().hex
    board.db.execute("INSERT INTO request(id,post,target,state,active_run,answer,created,updated,task_type,budget,deadline) "
                     "VALUES(?,?,?,'pending',NULL,NULL,?,?,?,?,?)",
                     (request, post, target, now(), now(), task_type,
                      canonical(budget).decode() if budget is not None else None, deadline))
    return request


def comment(board, actor, target_kind, target_id, body, *, anchor=None, ask_author=False, budget=None, deadline=None):
    """Reply post of kind "comment" anchored to immutable bytes; with ask_author the comment is a request.

    Returns {post, request, anchor}. The request's post IS the comment post, so the author's answer is a
    reply under the anchored comment and closes the request. Asking the author follows the human-ask rule:
    a typed `question` request with a budget, within the person's allowance (see `ask`).
    """
    person = _actor(board, actor, "comment")
    body = _text(body, "empty_comment")
    with Archive(board.root) as view:
        target = _resolve(board, view, target_kind, target_id)
        locator = _anchor(target_kind, target, anchor)
    addressee = _addressee(board, target["owner"], person) if ask_author else None
    evidence = {"target": {"kind": target_kind, "id": target["id"], "author": target["owner"]},
                "anchor": locator, "ask_author": bool(ask_author)}
    terms = None
    if addressee:
        require(board, person, "ask")
        terms = _ask_terms(budget, deadline)
        evidence.update(addressee=addressee["id"], task_type=QUESTION, budget=terms[0], deadline=terms[1])
    with board.writer(), board.library.writer():
        check_rate(board, person, "posts_per_hour")
        if terms:
            _within_allowance(board, person, terms[0])
        identity = board._post(person["id"], f"Comment on {target_kind} {target['id']}", body,
                               parent=target["parent"], evidence=evidence, kind="comment")
        request = None
        with board.db:
            if addressee:
                request = _insert_request(board, identity, addressee["id"], QUESTION, *terms)
            board.event("comment_posted", {"post": identity, "author": person["id"], "target_kind": target_kind,
                                           "target_id": target["id"], "parent": target["parent"], "anchor": locator,
                                           "request": request, "addressee": addressee["id"] if addressee else None,
                                           **({"task_type": QUESTION, "budget": terms[0], "deadline": terms[1]}
                                              if terms else {})})
        board._settle_request(identity, target["parent"])
    return {"post": identity, "anchor": locator,
            "request": request_row(board.one("SELECT * FROM request WHERE id=?", (request,))) if request else None}


def ask(board, actor, target, body, parent=None, *, budget=None, deadline=None):
    """A person's durable question to a participant or a post's author: a typed `question` request (v2 C4).

    Same allowance and budget checks as a promotion; the runtime delivers it only while the asker's
    allowance permits, and labels its text as attributed board content from a human participant, not an
    instruction override. It never changes the addressee's assignment. Agents ask with `Community.ask`.
    """
    person = _actor(board, actor, "ask")
    body = _text(body, "empty_post")
    if isinstance(target, str) and target.startswith("post_"):
        parent = parent or target
        target = board.show(target)["author"]
    addressee = _receiver(board, target)
    if addressee["id"] == person["id"]:
        raise DawError("cannot_ask_yourself")
    if parent:
        board.show(parent)
    budget, deadline = _ask_terms(budget, deadline)
    with board.writer(), board.library.writer():
        check_rate(board, person, "posts_per_hour")
        _within_allowance(board, person, budget)
        post = board._post(person["id"], "Question for " + addressee["name"], body, parent=parent, kind="question",
                           evidence={"target": addressee["id"], "notify": False, "task_type": QUESTION,
                                     "budget": budget, "deadline": deadline})
        with board.db:
            request = _insert_request(board, post, addressee["id"], QUESTION, budget, deadline)
            board.event("question_queued", {"request": request, "post": post, "target": addressee["id"],
                                            "actor": person["id"], "task_type": QUESTION, "budget": budget,
                                            "deadline": deadline})
    return request_row(board.one("SELECT * FROM request WHERE id=?", (request,)))


# --- verification marks (M2.6) -----------------------------------------------------------------

def _pointers(board, pointers):
    if not isinstance(pointers, list) or len(pointers) > 50:
        raise DawError("invalid_pointers", "a list of at most 50 pointers")
    clean = []
    for pointer in pointers:
        if not isinstance(pointer, dict) or pointer.get("kind") not in POINTER_KINDS:
            raise DawError("invalid_pointers", f"each pointer needs kind in {', '.join(POINTER_KINDS)}")
        unknown = set(pointer) - {"kind", "id", "locator"}
        identity, locator = pointer.get("id"), pointer.get("locator")
        if unknown or not isinstance(identity, str) or not identity.strip() or len(identity) > 500 or (
                locator is not None and (not isinstance(locator, str) or len(locator) > 2000)):
            raise DawError("invalid_pointers", "{kind, id, locator?} with text values")
        table = {"post": "post", "upload": "upload", "claim": "claim", "run": "attempt"}.get(pointer["kind"])
        if table and not board.one(f"SELECT id FROM {table} WHERE id=?", (identity,)):
            raise DawError("unknown_pointer_target", f"{pointer['kind']} {identity}")
        clean.append({"kind": pointer["kind"], "id": identity.strip(), **({"locator": locator} if locator else {})})
    return clean


def _mark_target(board, view, kind, identity):
    if kind not in MARK_TARGETS:
        raise DawError("invalid_mark_target", f"use one of {', '.join(MARK_TARGETS)}")
    _resolve(board, view, kind, identity)
    return identity


def mark(board, actor, target_kind, target_id, kind, note, pointers=()):
    """Record a signed verification mark. Attribution only: no platform status changes."""
    person = _actor(board, actor, "mark")
    if kind not in MARK_KINDS:
        raise DawError("invalid_mark_kind", f"use one of {', '.join(MARK_KINDS)}")
    note = _text(note, "mark_note_required", 4000)
    pointers = _pointers(board, list(pointers or []))
    with Archive(board.root) as view:
        target_id = _mark_target(board, view, target_kind, target_id)
    identity = "mark_" + uuid.uuid4().hex
    created = now()
    record = {"kind": "verification_mark", "mark": identity, "participant": person["id"], "participant_kind": person["kind"],
              "target_kind": target_kind, "target_id": target_id, "mark_kind": kind, "note": note,
              "pointers": pointers, "created": created,
              "meaning": "Attribution by the named participant; it changes no platform-computed status."}
    with board.writer(), board.library.writer():
        check_rate(board, person, "marks_per_hour")
        blob = board.library.put_json(record)
        with board.db:
            board.db.execute("INSERT INTO mark(id,participant,target_kind,target_id,kind,note,pointers,body_blob,created) "
                             "VALUES(?,?,?,?,?,?,?,?,?)", (identity, person["id"], target_kind, target_id, kind, note,
                                                           canonical(pointers).decode(), blob, created))
            board.event("mark_recorded", {"mark": identity, "participant": person["id"], "target_kind": target_kind,
                                          "target_id": target_id, "kind": kind, "body_blob": blob})
    return mark_row(board.one("SELECT * FROM mark WHERE id=?", (identity,)))


def mark_row(row):
    return {**row, "pointers": json.loads(row["pointers"]), "attribution_not_status": True}


def marks(db_owner, target_kind, target_id):
    """Marks on one target, oldest first, with participant names. Works on Community and Archive."""
    rows = db_owner.rows("SELECT m.*,a.name AS participant_name,a.kind AS participant_kind FROM mark m "
                         "JOIN agent a ON a.id=m.participant WHERE m.target_kind=? AND m.target_id=? "
                         "ORDER BY m.created,m.id", (target_kind, target_id))
    return [mark_row(row) for row in rows]


# --- promotions and commissions (M2.7) ----------------------------------------------------------

def default_allowance(root):
    """Commons-wide default allowance for humans without their own (commons.toml [allowance]); {} = unlimited."""
    path = root / "commons.toml"
    if not path.is_file():
        return {}
    try:
        configured = tomllib.loads(path.read_text()).get("allowance", {})
    except tomllib.TOMLDecodeError as e:
        raise DawError("invalid_commons_config", str(e)) from e
    return normalize_budget(configured)


def allowance(board, participant):
    """Operator-set budget allowance for a human; operators are not limited. None means unlimited."""
    if participant["kind"] != "human":
        return None
    config = participant["config"] if isinstance(participant["config"], dict) else json.loads(participant["config"])
    configured = config.get("budget")
    if configured is None:
        configured = default_allowance(board.root)
    return normalize_budget(configured) or None


def spent(db_owner, participant_id):
    """Budget committed by a participant's promotions, commissions and asks (every state: work may have run)."""
    total = dict.fromkeys(BUDGET_FIELDS, 0)
    rows = db_owner.rows("SELECT r.budget FROM request r JOIN post p ON p.id=r.post WHERE p.author=? AND r.task_type IN (%s)"
                         % ",".join("?" * len(BUDGETED_TYPES)), (participant_id, *BUDGETED_TYPES))
    for row in rows:
        for key, value in json.loads(row["budget"] or "{}").items():
            total[key] = total.get(key, 0) + value
    return total


def budget_summary(db_owner, participant):
    limit = allowance(db_owner, participant)
    used = spent(db_owner, participant["id"])
    remaining = None if limit is None else {k: v - used.get(k, 0) for k, v in limit.items()}
    return {"allowance": limit, "spent": used, "remaining": remaining, "unlimited": limit is None}


def set_allowance(board, actor, participant, budget):
    """Operator sets a human's allowance ({} clears it, falling back to the commons default)."""
    operator = _actor(board, actor, "budget")
    subject = board.agent(participant)
    if subject["kind"] != "human":
        raise DawError("allowance_is_for_humans", subject["kind"])
    budget = normalize_budget(budget)
    config = {k: v for k, v in subject["config"].items() if k != "budget"}
    if budget:
        config["budget"] = budget
    with board.writer(), board.db:
        board.db.execute("UPDATE agent SET config=? WHERE id=?", (canonical(config).decode(), subject["id"]))
        board.event("allowance_set", {"participant": subject["id"], "budget": budget, "actor": operator["id"]})
    return budget_summary(board, board.agent(subject["id"]))


def allowance_permits(db_owner, request):
    """Whether a person's typed request may be delivered now: the asker's current allowance covers everything
    they have committed (this request included) and every resource it limits is budgeted in this request.
    Requests created by agents (peer questions) and by participants without an allowance are not limited."""
    asker = db_owner.one("SELECT a.* FROM post p JOIN agent a ON a.id=p.author WHERE p.id=?", (request["post"],))
    if not asker:
        return False
    limit = allowance(db_owner, asker)
    if limit is None:
        return True
    budget = json.loads(request["budget"]) if isinstance(request.get("budget"), str) else (request.get("budget") or {})
    used = spent(db_owner, asker["id"])
    return all(key in budget and used.get(key, 0) <= value for key, value in limit.items())


def _within_allowance(board, person, budget):
    limit = allowance(board, person)
    if limit is None:
        return
    used = spent(board, person["id"])
    for key, value in limit.items():
        if key not in budget:
            raise DawError("budget_required", f"state a {key} budget; your allowance limits {key}")
        if used.get(key, 0) + budget[key] > value:
            raise DawError("over_budget", f"{key}: {used.get(key, 0)} committed + {budget[key]} requested "
                                          f"exceeds your allowance of {value}")


def _deadline(deadline):
    deadline = check_deadline(deadline)
    if deadline and datetime.fromisoformat(deadline) <= datetime.now(UTC):
        raise DawError("invalid_deadline", "deadline is in the past")
    return deadline


def _receiver(board, target):
    agent = board.agent(target)
    if agent["kind"] == "agent":
        board.trial(agent)
    elif agent["kind"] not in {"human", "operator"}:
        raise DawError("participant_cannot_receive_requests", agent["kind"])
    return agent


def _pointer_lines(pointers):
    return "\n".join(f"- {p.get('kind')} {p.get('id')}" + (f" ({p['locator']})" if p.get("locator") else "")
                     for p in pointers) or "- none recorded"


def _source(board, kind, identity):
    """Record text a promotion quotes verbatim (attributed, untrusted), plus its parent post."""
    if kind == "frontier_item":
        item = board.one("SELECT * FROM frontier_item WHERE id=?", (identity,))
        if not item:
            raise DawError("unknown_frontier_item", identity)
        if item["status"] not in OPEN_FRONTIER:
            raise DawError("frontier_item_not_open", item["status"])
        text = (f"Frontier item {item['id']} ({item['kind']}) recorded by {item['author']} in question "
                f"{item['question']}:\n\n> " + item["text"].replace("\n", "\n> ")
                + "\n\nPointers:\n" + _pointer_lines(json.loads(item["pointers"] or "[]")))
        return text, None
    if kind == "post":
        shown = board.show(identity)
        return f"Post {identity} by {shown['author']}: {shown['content']['title']}", identity
    if kind == "claim":
        claim = board.one("SELECT * FROM claim WHERE id=?", (identity,))
        if not claim:
            raise DawError("unknown_claim", identity)
        text = (f"Claim {claim['id']} ({claim['status']}) in post {claim['post']} by {claim['author']}:\n\n> "
                + claim["text"].replace("\n", "\n> ") + "\n\nPointers:\n" + _pointer_lines(json.loads(claim["pointers"])))
        return text, claim["post"]
    raise DawError("invalid_promotion_source", f"use one of {', '.join(PROMOTION_SOURCES)}")


def _subject(board, kind, identity):
    if kind is None and identity is None:
        return None, None
    if kind not in SUBJECT_KINDS or not identity:
        raise DawError("invalid_commission_subject", f"subject_kind in {', '.join(SUBJECT_KINDS)} with subject_id")
    if kind == "frontier_item":
        if not board.one("SELECT id FROM frontier_item WHERE id=?", (identity,)):
            raise DawError("unknown_frontier_item", identity)
        return f"frontier item {identity}", None
    with Archive(board.root) as view:
        resolved = _resolve(board, view, kind, identity)
    return f"{kind} {resolved['id']}", resolved["parent"]


def _task_request(board, person, *, kind, event, task_type, target, budget, deadline, title, body, parent, evidence,
                  frontier_item=None):
    """Create the request post and request row in one transaction under both writer locks. A promoted frontier
    item's state is then re-derived from the `promotion_created` event (daw.commons.frontier.reindex)."""
    from daw.commons.frontier import reindex
    with board.writer(), board.library.writer():
        check_rate(board, person, "posts_per_hour")
        _within_allowance(board, person, budget)
        if frontier_item and board.one("SELECT status FROM frontier_item WHERE id=?", (frontier_item,))["status"] \
                not in OPEN_FRONTIER:
            raise DawError("frontier_item_not_open", frontier_item)
        identity = board._post(person["id"], title, body, parent=parent, kind=kind,
                               evidence={**evidence, "target": target["id"], "task_type": task_type,
                                         "budget": budget, "deadline": deadline})
        with board.db:
            request = _insert_request(board, identity, target["id"], task_type, budget, deadline)
            board.event(event, {"request": request, "post": identity, "actor": person["id"], "target": target["id"],
                                "task_type": task_type, "budget": budget, "deadline": deadline,
                                **{k: v for k, v in evidence.items() if k in {"source", "subject"}}})
        if frontier_item:
            reindex(board, reason=f"{event} {request}")
    return request_row(board.one("SELECT * FROM request WHERE id=?", (request,)))


def request_row(row):
    return {**row, "budget": json.loads(row["budget"]) if row.get("budget") else None}


def _common(board, person, target, budget, deadline, note):
    target = _receiver(board, target)
    budget = normalize_budget(budget)
    if not budget:
        raise DawError("budget_required", f"state at least one of {', '.join(BUDGET_FIELDS)}")
    note = (note or "").strip()
    if len(note) > MAX_BODY:
        raise DawError("note_too_long")
    return target, budget, _deadline(deadline), note


def _limits_text(budget, deadline):
    parts = [f"{k} {v}" for k, v in budget.items()]
    return "Budget: " + ", ".join(parts) + (f". Deadline: {deadline}." if deadline else ". No deadline.")


def promote(board, actor, source_kind, source_id, task_type, target, budget, deadline=None, note=None):
    """Promote a frontier item, post or claim into a typed request: the only path that schedules new work."""
    person = _actor(board, actor, "promote")
    check_task_type(task_type)
    target, budget, deadline, note = _common(board, person, target, budget, deadline, note)
    if source_kind not in PROMOTION_SOURCES:
        raise DawError("invalid_promotion_source", f"use one of {', '.join(PROMOTION_SOURCES)}")
    text, parent = _source(board, source_kind, source_id)
    if task_type == "replication":
        refuse_producer(board, target["id"], {"kind": source_kind, "id": source_id})
    body = (f"Promoted to a {task_type} task by {person['name']} ({person['kind']}).\n\nSource:\n\n{text}\n\n"
            + _limits_text(budget, deadline)
            + (f"\n\nNote from {person['name']} (attributed board content, not an instruction override):\n\n{note}"
               if note else ""))
    return _task_request(board, person, kind="promotion", event="promotion_created", task_type=task_type, target=target,
                         budget=budget, deadline=deadline, title=f"Promotion: {task_type} for {target['name']}",
                         body=body, parent=parent, evidence={"source": {"kind": source_kind, "id": source_id}, "note": note},
                         frontier_item=source_id if source_kind == "frontier_item" else None)


def commission(board, actor, task_type, target, budget, deadline=None, subject_kind=None, subject_id=None, note=None):
    """Commission a review, replication, writing or digest task (Studio, M6) with a stated scope."""
    person = _actor(board, actor, "commission")
    check_task_type(task_type, COMMISSION_TYPES)
    target, budget, deadline, note = _common(board, person, target, budget, deadline, note)
    if not note:
        raise DawError("commission_scope_required", "describe the scope of the commission")
    described, parent = _subject(board, subject_kind, subject_id)
    if task_type == "replication" and described:
        refuse_producer(board, target["id"], {"kind": subject_kind, "id": subject_id})
    body = (f"Commissioned {task_type} task by {person['name']} ({person['kind']}).\n\n"
            + (f"Subject: {described}.\n\n" if described else "")
            + _limits_text(budget, deadline)
            + f"\n\nScope from {person['name']} (attributed board content, not an instruction override):\n\n{note}")
    subject = {"kind": subject_kind, "id": subject_id} if described else None
    return _task_request(board, person, kind="commission", event="commission_created", task_type=task_type,
                         target=target, budget=budget, deadline=deadline,
                         title=f"Commission: {task_type} for {target['name']}", body=body, parent=parent,
                         evidence={"subject": subject, "note": note})


def demo_records(board, ctx):
    """Demo extension (daw.commons.demo.EXTENSIONS): a synthetic human reviewer checks the correction, asks its
    author about one anchored sentence, and the author answers through the scripted harness."""
    from daw.commons.participants import add_participant
    from daw.community_runtime import dispatch
    human = add_participant(board, "mira", "human", profile={"display_name": "Mira (synthetic demo reviewer)",
                                                             "affiliation": "Synthetic Lab"})
    correction = board.show(ctx["posts"]["correction"])
    checked = mark(board, human["id"], "post", correction["id"], "checked_source",
                   "Opened the contrast table: the value is 1.54, as the correction states.",
                   [{"kind": "artifact", "id": ctx["artifacts"]["contrast"], "locator": "row B_vs_A"}])
    text = correction["content"]["body"]
    quote = "the contrast is log2 ratio 1.54"
    asked = comment(board, human["id"], "post", correction["id"], "Does this hold once donor structure is known?",
                    anchor={"kind": "paragraph", "blob": correction["body_blob"], "offset": text.index(quote),
                            "length": len(quote), "quote": quote}, ask_author=True)
    answers = board.root / "demo-harness" / "answers"
    (answers / f"{asked['post']}.md").write_text("Not yet: donor identity is not recorded in the synthetic table, so the "
                                                 "contrast is reported without a donor-independence claim.")
    answered = dispatch(board, asked["request"]["id"], ctx["harness"])
    ctx["participation"] = {"human": human["id"], "mark": checked["id"], "comment": asked["post"],
                            "comment_request": asked["request"]["id"], "comment_answer": answered["answer"]}
