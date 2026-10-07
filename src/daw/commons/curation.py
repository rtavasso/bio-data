"""Curated pointers (spec v3 G2): a person points a number at the bytes it came from, or marks it unlocatable.

The platform never authors pointers; people do. A curator reads a final, finds where one of its numbers comes
from (the curation locator, `tour.candidates`, lists candidate cells, keys and lines in the artifacts the post
names) and records it:

- `curate(board, person, post, offset, artifact=…, locator=…, note=…)` records a **pointer_curated** mark;
- `curate(…, unlocatable=True, note=…)` records an **unlocatable** mark (no artifact the post names holds the
  value, the bytes are not in this archive, the value was computed in prose, …), with the curator's reason.

Each act is a `mark` row on the post (kind `pointer_curated` or `unlocatable`; target the post; the artifact
and locator as its pointer), a body blob in the library and one `pointer_curated` board event carrying the
participant, post, number offset and text, artifact, locator and note. Only humans and operators curate
(permission `curate`; visitors and agents are refused); the HTTP route takes the write discipline (`Actor`).

A curated pointer is checked before it is recorded: the post is visible, the checker detects a number at the
offset, the artifact is among the evidence the post names, the locator names a cell, JSON key or line (a
curator reads the place, never "anywhere in the file"), and `locators.verify_artifact` finds the value there in
the sha256-checked bytes. Every read re-checks it the same way.

The checker (`checks.post_numbers`) reads the latest act per (post, offset): a curated pointer on a number the
author did not point gives it scope `curated`, shown with the curator's name; it is never counted as the
author's pointer, in `verified_share` or in the number-level share. A number with an author pointer keeps its
scope and lists the curated pointer beside it. An unlocatable mark keeps the number's scope and status and
attaches the curator's note. Recording is append-only; a later act on the same number supersedes the earlier
one for display, and both stay in the record.
"""
import json
import uuid
from urllib.parse import quote

from daw.util import DawError, canonical, now

EVENT = "pointer_curated"
KINDS = ("pointer_curated", "unlocatable")
AUTHOR_SCOPES = ("cell", "claim", "line", "text")
MAX_NOTE = 4000
MILESTONE_FINALS = 5


def _note(value):
    value = (value or "").strip()
    if not value or len(value) > MAX_NOTE:
        raise DawError("curation_note_required", f"a note is required (at most {MAX_NOTE} characters)")
    return value


def check(view, post, offset, *, artifact=None, locator=None, unlocatable=False, caller=None):
    """Validate one curation act against the archive; returns {number, verification?}. Raises DawError."""
    from daw.commons import checks, locators, views
    row = views.thread_index(view)["posts"].get(post)
    if not row:
        raise DawError("unknown_post", post)
    vis = views.visibility(view, caller)
    if vis.withheld(post):
        raise DawError("hidden_by_moderation", post)
    if vis.refused(post):
        raise DawError("writeup_withheld", "a refused write-up is withheld; its numbers are not curated")
    content = row["content"]
    body = content.get("body") or ""
    number = next((n for n in checks.post_numbers(view, post, body, content.get("evidence"), curated=False)
                   if n["offset"] == offset), None)
    if number is None:
        raise DawError("unknown_number", f"the checker detects no number at offset {offset}")
    if unlocatable:
        if artifact or locator:
            raise DawError("invalid_curation", "an unlocatable mark names no artifact or locator")
        return {"number": number}
    if not artifact or not locator:
        raise DawError("invalid_curation", "a curated pointer names an artifact and a locator (or mark the number "
                                           "unlocatable)")
    try:
        parsed = locators.parse_locator(locator)
    except locators.LocatorError as error:
        raise DawError("invalid_locator", str(error)) from error
    if locators.target_kind(parsed) is None:
        raise DawError("invalid_locator", "name the place: a cell (row=;col=), a JSON key (key=) or a line (line=)")
    named = [p["id"] for p in checks.post_evidence(view, post, body, content.get("evidence")) if p["kind"] == "artifact"]
    if artifact not in named:
        raise DawError("artifact_not_named_by_post", "a curated pointer cites an artifact the post names as evidence")
    result = locators.verify_artifact(view, artifact, locator, locators.parse_number(number["text"]), {})
    if result["result"] != "verified":
        raise DawError("value_not_at_locator", result.get("reason") or "the value is not at the locator")
    return {"number": number, "verification": result}


def curate(board, actor, post, offset, *, artifact=None, locator=None, note=None, unlocatable=False):
    """Record one curation act (see the module docstring). Returns the act as `acts` reads it."""
    from daw.commons.archive import Archive
    from daw.commons.moderation import check_rate
    from daw.commons.permissions import require
    person = require(board, board.agent(actor), "curate")
    note = _note(note)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise DawError("invalid_curation", "offset is a non-negative integer")
    artifact = (artifact or "").strip() or None
    locator = (locator or "").strip() or None
    with Archive(board.root) as view:
        checked = check(view, post, offset, artifact=artifact, locator=locator, unlocatable=unlocatable, caller=person)
    number = checked["number"]
    kind = "unlocatable" if unlocatable else "pointer_curated"
    identity = "mark_" + uuid.uuid4().hex
    created = now()
    pointers = [] if unlocatable else [{"kind": "artifact", "id": artifact, "locator": locator}]
    record = {"kind": "curated_pointer", "mark": identity, "participant": person["id"],
              "participant_kind": person["kind"], "post": post, "offset": offset, "text": number["text"],
              "mark_kind": kind, "artifact": artifact, "locator": locator, "note": note, "created": created,
              "verification": {k: v for k, v in (checked.get("verification") or {}).items() if k in ("result", "at", "found")},
              "meaning": "A person's pointer at a number (or a number marked unlocatable): attributed to them, never "
                         "the author's pointer and never counted as author-verified."}
    with board.writer(), board.library.writer():
        check_rate(board, person, "marks_per_hour")
        blob = board.library.put_json(record)
        with board.db:
            board.db.execute("INSERT INTO mark(id,participant,target_kind,target_id,kind,note,pointers,body_blob,created) "
                             "VALUES(?,?,?,?,?,?,?,?,?)", (identity, person["id"], "post", post, kind, note,
                                                           canonical(pointers).decode(), blob, created))
            board.event(EVENT, {"mark": identity, "participant": person["id"], "post": post, "offset": offset,
                                "text": number["text"], "kind": kind, "artifact": artifact, "locator": locator,
                                "note": note, "body_blob": blob})
    return {"mark": identity, "participant": person["id"], "participant_name": person["name"], "post": post,
            "offset": offset, "text": number["text"], "kind": kind, "artifact": artifact, "locator": locator,
            "note": note, "created": created, "body_blob": blob}


# ---------------------------------------------------------------------------- reading (never writes)

def acts(view):
    """{post: {offset: latest act}} from `pointer_curated` events, with curator names. Cached per sequence."""
    from daw.commons.checks import _cached

    def compute():
        names = {r["id"]: r["name"] for r in view.rows("SELECT id,name FROM agent")}
        latest = {}
        for row in view.rows("SELECT seq,body,created FROM event WHERE kind=? ORDER BY seq", (EVENT,)):
            body = json.loads(row["body"])
            latest.setdefault(body["post"], {})[body["offset"]] = {
                **body, "seq": row["seq"], "created": row["created"],
                "participant_name": names.get(body["participant"], body["participant"])}
        return latest
    return _cached(("curation", str(view.root), view.sequence()), compute)


def history(view, post):
    """Every act on one post, oldest first (the record; `acts` keeps the latest per number)."""
    names = {r["id"]: r["name"] for r in view.rows("SELECT id,name FROM agent")}
    out = []
    for row in view.rows("SELECT seq,body,created FROM event WHERE kind=? ORDER BY seq", (EVENT,)):
        body = json.loads(row["body"])
        if body["post"] == post:
            out.append({**body, "seq": row["seq"], "created": row["created"],
                        "participant_name": names.get(body["participant"], body["participant"])})
    return out


def _attribution(act):
    return {"mark": act["mark"], "curator": act["participant"], "curator_name": act["participant_name"],
            "note": act["note"], "created": act["created"], "curated": True}


def overlay(view, post, records, located):
    """Apply the latest curation acts of a post to its number records (copies; the verdict is untouched)."""
    from daw.commons import locators, views
    latest = acts(view).get(post)
    if not latest:
        return records
    out, outputs = [], {}
    for record in records:
        act = latest.get(record["offset"])
        if not act or act["text"] != record["text"]:
            out.append(record)  # no act, or an act recorded under other rules that no longer names this number
            continue
        if act["kind"] == "unlocatable":
            out.append({**record, "unlocatable": _attribution(act)})
            continue
        aid, locator = act["artifact"], act["locator"]
        result = locators.verify_artifact(view, aid, locator, locators.parse_number(record["text"]), outputs)
        if aid not in located:
            located[aid] = views.locate_artifact(view, aid, quiet=True)
        pointer = {"kind": "artifact", "id": aid, "artifact": aid, "locator": locator, "location": located[aid],
                   "route": f"/artifact/{aid}?locator={quote(locator, safe='')}", **_attribution(act),
                   **{k: v for k, v in result.items() if k in ("result", "at", "reason", "found")}}
        if record["scope"] in AUTHOR_SCOPES:
            out.append({**record, "curated_pointers": [pointer]})  # the author's pointer stays the number's scope
            continue
        status = "verified" if result["result"] == "verified" else "unverified"
        entry = {k: v for k, v in record.items() if k != "reason"}
        out.append({**entry, "scope": "curated", "status": status, "pointers": [pointer],
                    **({} if status == "verified" else {"reason": result.get("reason")})})
    return out


def progress(view, posts):
    """Per post: numbers, author pointers, curated pointers, unlocatable and unresolved numbers (counts and the
    unresolved numbers' offsets). Hidden posts and withheld write-ups report nothing (not zero)."""
    from daw.commons import checks, views
    index = views.thread_index(view)
    vis = views.visibility(view)
    rows = []
    for pid in posts:
        row = index["posts"].get(pid)
        if not row or vis.withheld(pid) or vis.refused(pid):
            rows.append({"post": pid, "available": False})
            continue
        content = row["content"]
        numbers = checks.post_numbers(view, pid, content.get("body") or "", content.get("evidence"))
        author = [n for n in numbers if n["scope"] in AUTHOR_SCOPES and n["status"] == "verified"]
        curated = [n for n in numbers if n["scope"] == "curated" and n["status"] == "verified"]
        unlocatable = [n for n in numbers if n.get("unlocatable") and n not in author and n not in curated]
        resolved = {n["offset"] for n in author + curated + unlocatable}
        unresolved = [n for n in numbers if n["offset"] not in resolved]
        curators = sorted({p["curator_name"] for n in numbers for p in n["pointers"] if p.get("curated")}
                          | {n["unlocatable"]["curator_name"] for n in unlocatable})
        rows.append({"post": pid, "available": True, "numbers": len(numbers), "author_verified": len(author),
                     "curated": len(curated), "unlocatable": len(unlocatable), "unresolved": len(unresolved),
                     "unresolved_numbers": [{"offset": n["offset"], "text": n["text"]} for n in unresolved],
                     "curators": curators, "resolved": bool(numbers) and not unresolved})
    return rows


def tour_finals(tour):
    return list(dict.fromkeys(step["final"] for step in tour["steps"]))


def receipt(view, tour, *, required=MILESTONE_FINALS):
    """The Milestone B receipt (spec v3 G2): for each of a tour's finals, every number resolved by an author
    pointer, curated by a person or marked unlocatable by a person. Counts and post ids only, no prose."""
    from daw.commons import writeup
    rows = progress(view, tour_finals(tour))
    for row in rows:
        row.pop("unresolved_numbers", None)
    resolved = [r for r in rows if r.get("resolved")]
    totals = {k: sum(r.get(k, 0) for r in rows) for k in ("numbers", "author_verified", "curated", "unlocatable",
                                                          "unresolved")}
    return {"receipt": "cohort-curation", "format": "colloquy.curation-receipt/1", "rules": writeup.RULES_VERSION,
            "board_sequence": view.sequence(), "tour": {"name": tour["name"], "curator": tour["curator"].get("name")},
            "finals": rows, "totals": totals,
            "milestone": {"required_finals": required, "resolved_finals": len(resolved),
                          "met": len(resolved) >= required},
            "definitions": {
                "author_verified": "verified through the author's own pointer at the number (cell, claim, line or text)",
                "curated": "verified through a person's curated pointer (pointer_curated mark), attributed to them",
                "unlocatable": "marked unlocatable by a person, with their note",
                "unresolved": "none of the above; a final is resolved when it has numbers and none is unresolved"}}
