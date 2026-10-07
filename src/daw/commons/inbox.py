"""A person's inbox (spec v2 V4): what happened to the things they asked, wrote, marked and promoted.

Every item is computed from a recorded relation, never inferred from text or timing:

| kind         | relation                                                                                     |
|--------------|----------------------------------------------------------------------------------------------|
| `answer`     | a `request` whose post the person authored (ask, comment to the author, promotion, commission) |
|              | has `answer` set: the answer post                                                              |
| `reply`      | a post whose `parent` is one of the person's posts, or whose `evidence.in_reply_to` names one    |
|              | (replies under an anchor), by someone else; replies under the person's comments say so         |
| `correction` | a post whose `supersedes` is a post the person marked, or the post of a claim they marked (a     |
|              | `mark` row), or that withdrew a claim they marked (`claim.withdrawn_by`)                       |
| `watcher_hit`| a `watcher_ran` event with new hits on a frontier item the person promoted (`promotion_created`  |
|              | naming the item), recorded after the promotion                                                 |

Each item carries `seq`, the board event sequence of the record that put it there (the answer's or reply's
`published` event, the `watcher_ran` event), so `GET /api/me/inbox?after=<seq>` and the per-caller SSE stream
resume like the board stream. Titles resolve through `moderation.Visibility`: a hidden post is an id and a
reason. Read state is one immutable `inbox_read` row per person and item, written only by the person's own
`mark_read` (permission `inbox`, one `inbox_marked_read` event); unread is the absence of a row.
"""
import json

from daw.commons.permissions import require
from daw.util import DawError, now

KINDS = ("answer", "reply", "correction", "watcher_hit")
MAX_MARK = 500


def _published(view):
    """{post id: seq of its `published` event}."""
    return {row["post"]: row["seq"] for row in view.rows(
        "SELECT seq,json_extract(body,'$.post') AS post FROM event WHERE kind='published'")}


def _title(vis, index, pid):
    row = index["posts"].get(pid)
    return vis.title(pid, row["content"].get("title")) if row else None


def _post_fields(vis, index, pid, published):
    row = index["posts"].get(pid)
    return {"post": pid, "title": _title(vis, index, pid), "author": row["author"] if row and not vis.withheld(pid)
            else None, "created": row["created"] if row else None, "hidden": vis.hidden(pid),
            "reason": vis.reason(pid), "seq": published.get(pid)}


def items(view, participant, *, caller=None):
    """Every inbox item of `participant` (an agent row or id), newest first, without read state."""
    from daw.commons.views import thread_index, visibility
    pid = participant if isinstance(participant, str) else participant["id"]
    index = thread_index(view)
    vis = visibility(view, caller)
    published = _published(view)
    mine = {p for p, row in index["posts"].items() if row["author"] == pid}
    out = {}

    # Answers to the person's asks, comments to authors, promotions and commissions.
    for row in view.rows("SELECT r.id,r.post,r.answer,r.task_type,r.target,r.state FROM request r JOIN post p ON "
                         "p.id=r.post WHERE p.author=? AND r.answer IS NOT NULL ORDER BY r.created,r.id", (pid,)):
        answer = row["answer"]
        if answer not in index["posts"] or index["posts"][answer]["author"] == pid:
            continue
        asked = index["posts"].get(row["post"], {}).get("content", {})
        out[f"answer:{row['id']}"] = {
            "kind": "answer", **_post_fields(vis, index, answer, published), "request": row["id"],
            "task_type": row["task_type"], "asked": row["post"], "asked_kind": asked.get("kind"),
            "relation": {"table": "request", "id": row["id"], "field": "answer"}}
    answers = {item["post"] for item in out.values()}

    # Replies to the person's posts (including replies under an anchor that name the post they answer).
    for post, row in index["posts"].items():
        if row["author"] == pid or post in answers:
            continue
        evidence = row["content"].get("evidence") if isinstance(row["content"].get("evidence"), dict) else {}
        target = evidence.get("in_reply_to") if evidence.get("in_reply_to") in mine else row["parent"]
        if target not in mine:
            continue
        parent_kind = index["posts"][target]["content"].get("kind")
        out[f"reply:{post}"] = {
            "kind": "reply", **_post_fields(vis, index, post, published), "in_reply_to": target,
            "to_comment": parent_kind == "comment", "anchored": bool(evidence.get("anchor")) and not vis.withheld(post),
            "relation": {"table": "post", "id": post,
                         "field": "evidence.in_reply_to" if evidence.get("in_reply_to") == target else "parent"}}

    # Corrections to posts (and claims) the person marked.
    marked = view.rows("SELECT id,target_kind,target_id FROM mark WHERE participant=? AND target_kind IN "
                       "('post','claim') ORDER BY created,id", (pid,))
    for mark in marked:
        corrected, withdrawn_by = mark["target_id"], None
        if mark["target_kind"] == "claim":
            claim = view.one("SELECT post,withdrawn_by FROM claim WHERE id=?", (mark["target_id"],))
            if not claim:
                continue
            corrected, withdrawn_by = claim["post"], claim["withdrawn_by"]
        candidates = list(index["superseded_by"].get(corrected, []))
        if withdrawn_by and withdrawn_by not in candidates:
            candidates.append(withdrawn_by)
        for post in candidates:
            if post not in index["posts"] or index["posts"][post]["author"] == pid:
                continue
            key = f"correction:{post}"
            item = out.setdefault(key, {"kind": "correction", **_post_fields(vis, index, post, published),
                                        "corrects": corrected, "marks": [], "relation": {
                                            "table": "post", "id": post,
                                            "field": "supersedes" if index["posts"][post]["supersedes"] == corrected
                                            else "claim.withdrawn_by"}})
            item["marks"].append({"mark": mark["id"], "target_kind": mark["target_kind"],
                                  "target_id": mark["target_id"]})

    # Watcher hits on frontier items the person promoted (after the promotion).
    promoted = {}
    for event in view.rows("SELECT seq,body FROM event WHERE kind='promotion_created' ORDER BY seq"):
        body = json.loads(event["body"])
        source = body.get("source") or {}
        if body.get("actor") == pid and source.get("kind") == "frontier_item":
            promoted.setdefault(source.get("id"), (event["seq"], body.get("request")))
    if promoted:
        for event in view.rows("SELECT seq,body,created FROM event WHERE kind='watcher_ran' ORDER BY seq"):
            body = json.loads(event["body"])
            since = promoted.get(body.get("item"))
            if not since or event["seq"] <= since[0] or not body.get("new"):
                continue
            notice = body.get("post")
            out[f"watcher_hit:{body.get('run')}"] = {
                "kind": "watcher_hit", "seq": event["seq"], "created": event["created"], "item": body.get("item"),
                "watcher": body.get("watcher"), "watcher_run": body.get("run"), "new": body.get("new"),
                "promotion": since[1], "post": notice, "title": _title(vis, index, notice) if notice else None,
                "hidden": vis.hidden(notice) if notice else False, "reason": vis.reason(notice) if notice else None,
                "author": "watcher", "third_party_text": "hit titles in the notice are provider text",
                "relation": {"table": "event", "kind": "watcher_ran", "seq": event["seq"],
                             "promotion": since[1]}}
    result = [{"id": key, **value} for key, value in out.items()]
    result.sort(key=lambda item: (item.get("seq") or 0, item["id"]), reverse=True)
    return result


def read_state(view, participant_id):
    return {row["item"]: row["read_at"] for row in view.rows(
        "SELECT item,read_at FROM inbox_read WHERE participant=?", (participant_id,))}


def inbox(view, participant, *, after=0, limit=200, caller=None, unread_only=False, scope=None):
    """The person's inbox with read state: items with seq > `after`, newest first."""
    from daw.commons import savedviews
    pid = participant["id"]
    every = items(view, participant, caller=caller or participant)
    read = read_state(view, pid)
    for item in every:
        item["read"] = item["id"] in read
        item["read_at"] = read.get(item["id"])
    if scope is not None:
        questions = _question_lookup(view, caller or participant)
        every, _ = savedviews.page(every, scope, lambda i: ({i.get("author")}, questions(i.get("post")),
                                                            i.get("created")))
    selected = [i for i in every if (i.get("seq") or 0) > after and (not unread_only or not i["read"])]
    return {"participant": pid, "items": selected[:limit], "total": len(selected),
            "unread": sum(1 for i in every if not i["read"]), "latest": max((i.get("seq") or 0 for i in every), default=0),
            "sequence": view.sequence(), "after": after, "kinds": KINDS,
            **({"view": scope.describe()} if scope is not None else {}),
            "note": "Computed from recorded relations (requests, parents, marks, promotions, watcher runs); "
                    "content is attributed and untrusted."}


def _question_lookup(view, caller):
    from daw.commons.savedviews import question_lookup
    return question_lookup(view, caller)


def mark_read(board, actor, keys=None, *, everything=False):
    """The person's own "mark read": one immutable row per item and one board event. Returns the new state."""
    from daw.commons.archive import Archive
    person = require(board, board.agent(actor), "inbox")
    with Archive(board.root) as view:
        current = {item["id"] for item in items(view, person, caller=person)}
        already = set(read_state(view, person["id"]))
    if everything:
        wanted = sorted(current - already)
    else:
        if not isinstance(keys, list) or not keys or len(keys) > MAX_MARK:
            raise DawError("invalid_inbox_items", f"name 1..{MAX_MARK} inbox items, or mark all")
        unknown = sorted(set(keys) - current)
        if unknown:
            raise DawError("unknown_inbox_item", ", ".join(unknown[:5]))
        wanted = sorted(set(keys) - already)
    stamp = now()
    with board.writer(), board.db:
        for key in wanted:
            board.db.execute("INSERT OR IGNORE INTO inbox_read(participant,item,read_at) VALUES(?,?,?)",
                             (person["id"], key, stamp))
        if wanted:
            board.event("inbox_marked_read", {"participant": person["id"], "count": len(wanted),
                                              "items": wanted[:MAX_MARK]})
    return {"participant": person["id"], "marked": wanted, "read_at": stamp if wanted else None}
