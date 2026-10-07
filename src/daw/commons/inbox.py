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

The SSE stream computes the full inbox only on (re)connect; afterwards it reads deltas from the events since its
cursor (`delta`, one shared event window per write, spec v3 B8).
"""
import json
import threading
from collections import OrderedDict

from daw.commons.permissions import require
from daw.util import DawError, now

KINDS = ("answer", "reply", "correction", "watcher_hit")
MAX_MARK = 500


def _published(view):
    """{post id: seq of its `published` event}."""
    return {row["post"]: row["seq"] for row in view.rows(
        "SELECT seq,json_extract(body,'$.post') AS post FROM event WHERE kind='published'")}


def _title(vis, posts, pid):
    row = posts(pid)
    return vis.title(pid, row["content"].get("title")) if row else None


def _post_fields(vis, posts, pid, published):
    row = posts(pid)
    return {"post": pid, "title": _title(vis, posts, pid), "author": row["author"] if row and not vis.withheld(pid)
            else None, "created": row["created"] if row else None, "hidden": vis.hidden(pid),
            "reason": vis.reason(pid), "seq": published(pid)}


ANSWERED = ("SELECT r.id,r.post,r.answer,r.task_type,r.target,r.state FROM request r JOIN post p ON p.id=r.post "
            "WHERE p.author=? AND r.answer IS NOT NULL")


class _Board:
    """Every record (the full inbox, computed on connect): posts from the thread index, every event."""

    def __init__(self, view):
        from daw.commons.views import thread_index
        self.view = view
        index = thread_index(view)
        self.index = index
        self.posts = index["posts"].get
        self.candidates = list(index["posts"])
        self.published = _published(view).get

    def superseded(self, pid):
        return self.index["superseded_by"].get(pid, [])

    def mine(self, pid):
        return {p for p, row in self.index["posts"].items() if row["author"] == pid}

    def answered(self, pid):
        return self.view.rows(ANSWERED + " ORDER BY r.created,r.id", (pid,))

    def withdrawing(self, post):
        return True

    def watcher_runs(self):
        return self.view.rows("SELECT seq,body,created FROM event WHERE kind='watcher_ran' ORDER BY seq")


def _collect(view, pid, vis, source):
    """Items of `pid`, newest first, from the records `source` offers (the whole board, or one event window)."""
    posts, published = source.posts, source.published
    mine = source.mine(pid)
    out = {}

    # Answers to the person's asks, comments to authors, promotions and commissions.
    for row in source.answered(pid):
        answer = row["answer"]
        found = posts(answer)
        if not found or found["author"] == pid:
            continue
        asked = (posts(row["post"]) or {}).get("content", {})
        out[f"answer:{row['id']}"] = {
            "kind": "answer", **_post_fields(vis, posts, answer, published), "request": row["id"],
            "task_type": row["task_type"], "asked": row["post"], "asked_kind": asked.get("kind"),
            "relation": {"table": "request", "id": row["id"], "field": "answer"}}
    answers = {item["post"] for item in out.values()}

    # Replies to the person's posts (including replies under an anchor that name the post they answer).
    for post in source.candidates:
        row = posts(post)
        if not row or row["author"] == pid or post in answers:
            continue
        evidence = row["content"].get("evidence") if isinstance(row["content"].get("evidence"), dict) else {}
        target = evidence.get("in_reply_to") if evidence.get("in_reply_to") in mine else row["parent"]
        if target not in mine:
            continue
        parent_kind = posts(target)["content"].get("kind")
        out[f"reply:{post}"] = {
            "kind": "reply", **_post_fields(vis, posts, post, published), "in_reply_to": target,
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
        candidates = list(source.superseded(corrected))
        if withdrawn_by and withdrawn_by not in candidates and source.withdrawing(withdrawn_by):
            candidates.append(withdrawn_by)
        for post in candidates:
            row = posts(post)
            if not row or row["author"] == pid:
                continue
            key = f"correction:{post}"
            item = out.setdefault(key, {"kind": "correction", **_post_fields(vis, posts, post, published),
                                        "corrects": corrected, "marks": [], "relation": {
                                            "table": "post", "id": post,
                                            "field": "supersedes" if row["supersedes"] == corrected
                                            else "claim.withdrawn_by"}})
            item["marks"].append({"mark": mark["id"], "target_kind": mark["target_kind"],
                                  "target_id": mark["target_id"]})

    # Watcher hits on frontier items the person promoted (after the promotion).
    runs = source.watcher_runs()
    promoted = {}
    for event in view.rows("SELECT seq,body FROM event WHERE kind='promotion_created' ORDER BY seq") if runs else ():
        body = json.loads(event["body"])
        promotion_source = body.get("source") or {}
        if body.get("actor") == pid and promotion_source.get("kind") == "frontier_item":
            promoted.setdefault(promotion_source.get("id"), (event["seq"], body.get("request")))
    for event in runs if promoted else ():
        body = json.loads(event["body"])
        since = promoted.get(body.get("item"))
        if not since or event["seq"] <= since[0] or not body.get("new"):
            continue
        notice = body.get("post")
        out[f"watcher_hit:{body.get('run')}"] = {
            "kind": "watcher_hit", "seq": event["seq"], "created": event["created"], "item": body.get("item"),
            "watcher": body.get("watcher"), "watcher_run": body.get("run"), "new": body.get("new"),
            "promotion": since[1], "post": notice, "title": _title(vis, posts, notice) if notice else None,
            "hidden": vis.hidden(notice) if notice else False, "reason": vis.reason(notice) if notice else None,
            "author": "watcher", "third_party_text": "hit titles in the notice are provider text",
            "relation": {"table": "event", "kind": "watcher_ran", "seq": event["seq"],
                         "promotion": since[1]}}
    result = [{"id": key, **value} for key, value in out.items()]
    result.sort(key=lambda item: (item.get("seq") or 0, item["id"]), reverse=True)
    return result


def items(view, participant, *, caller=None):
    """Every inbox item of `participant` (an agent row or id), newest first, without read state."""
    from daw.commons.views import visibility
    pid = participant if isinstance(participant, str) else participant["id"]
    return _collect(view, pid, visibility(view, caller), _Board(view))


# ---------------------------------------------------------------------------- deltas (spec v3 B8)
#
# A subscriber's stream computes its full inbox once, on (re)connect. After that each board change is read as the
# window of events (after, until]: the posts published in it (with their content), the requests answered in it and
# the watcher runs. One window is built per commons and cursor pair and shared by every subscriber at that cursor,
# so ten subscribers and one write cost one window build and no thread index build. Each subscriber then applies
# its own relations (its posts, asks, marks and promotions) with a few indexed queries on its own connection.

WINDOW_EVENTS = ("published", "answered_by_publication", "delivery_completed", "published_answer_recovered",
                 "watcher_ran")
WINDOW_SIZE = 32
_WINDOWS: "OrderedDict[tuple, Window]" = OrderedDict()
_WINDOW_LOCK = threading.Lock()
BUILDS = {"windows": 0}  # how many windows were built in this process (observed by the B8 test)


class Window:
    """Board records of the event window (after, until]. Plain data, shared by subscriber threads."""

    def __init__(self, view, after, until):
        from daw.commons.moderation import _refused_writeups
        from daw.commons.views import content
        self.after, self.until = after, until
        marks = ",".join("?" for _ in WINDOW_EVENTS)
        self.published, self.requests, self.runs = {}, set(), []
        for row in view.rows(f"SELECT seq,kind,body,created FROM event WHERE seq>? AND seq<=? AND kind IN ({marks}) "
                             "ORDER BY seq", (after, until, *WINDOW_EVENTS)):
            body = json.loads(row["body"])
            if row["kind"] == "published" and isinstance(body.get("post"), str):
                self.published[body["post"]] = row["seq"]
            elif row["kind"] == "watcher_ran":
                self.runs.append(row)
            elif isinstance(body.get("request"), str):
                self.requests.add(body["request"])
        self.posts, self.superseded = {}, {}
        for pid in self.published:
            row = view.one("SELECT * FROM post WHERE id=?", (pid,))
            if row:
                self.posts[pid] = {**row, "content": content(view, row["body_blob"])}
                if row["supersedes"]:
                    self.superseded.setdefault(row["supersedes"], []).append(pid)
        # Write-ups the number checker refused (C5), read once for every subscriber of this window.
        self.refused = _refused_writeups(view) if self.posts else {}


def window(view, after, until):
    """The shared window (after, until] of one commons, built once under a lock for every subscriber."""
    key = (str(view.root), after, until)
    with _WINDOW_LOCK:
        if key in _WINDOWS:
            _WINDOWS.move_to_end(key)
            return _WINDOWS[key]
        built = _WINDOWS[key] = Window(view, after, until)
        BUILDS["windows"] += 1
        while len(_WINDOWS) > WINDOW_SIZE:
            _WINDOWS.popitem(last=False)
        return built


class _Delta:
    """One subscriber's reading of a window: the window's posts, and any other post loaded by id on its own view."""

    def __init__(self, view, shared):
        self.view, self.shared = view, shared
        self.candidates = list(shared.posts)
        self.loaded, self.sequences = {}, {}

    def posts(self, pid):
        from daw.commons.views import content
        if pid in self.shared.posts:
            return self.shared.posts[pid]
        if pid not in self.loaded:
            row = self.view.one("SELECT * FROM post WHERE id=?", (pid,)) if isinstance(pid, str) else None
            self.loaded[pid] = {**row, "content": content(self.view, row["body_blob"])} if row else None
        return self.loaded[pid]

    def published(self, pid):
        if pid in self.shared.published:
            return self.shared.published[pid]
        if pid not in self.sequences:  # an answer published before the window and recorded as an answer in it
            row = self.view.one("SELECT seq FROM event WHERE kind='published' AND json_extract(body,'$.post')=?",
                                (pid,))
            self.sequences[pid] = row["seq"] if row else None
        return self.sequences[pid]

    def superseded(self, pid):
        return self.shared.superseded.get(pid, [])

    def mine(self, pid):
        return {r["id"] for r in self.view.rows("SELECT id FROM post WHERE author=?", (pid,))}

    def answered(self, pid):
        requests, answers = sorted(self.shared.requests), sorted(self.shared.posts)
        if not requests and not answers:
            return []
        return self.view.rows(ANSWERED + " AND (r.id IN (%s) OR r.answer IN (%s)) ORDER BY r.created,r.id"
                              % (",".join("?" * len(requests)) or "NULL", ",".join("?" * len(answers)) or "NULL"),
                              (pid, *requests, *answers))

    def withdrawing(self, post):
        return post in self.shared.posts

    def watcher_runs(self):
        return self.shared.runs


def delta(view, participant, after, until, *, caller=None):
    """Inbox items of `participant` that the events in (after, until] record, newest first, without read state:
    the relations of `items`, read from the shared window instead of the whole board."""
    from daw.commons.moderation import Visibility
    pid = participant if isinstance(participant, str) else participant["id"]
    shared = window(view, after, until)
    if not shared.posts and not shared.requests and not shared.runs:
        return []
    vis = Visibility.of(view, caller or participant)
    vis = Visibility(vis.records, reveal=vis.reveal, blobs=vis.blobs, refused=shared.refused)
    return _collect(view, pid, vis, _Delta(view, shared))


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
