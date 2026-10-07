"""Dialogue at anchors (spec v3 V12): the primary channel between people and the agents whose work they read.

A thread is a comment at an anchor (`participation.comment`, a `comment_posted` event without `in_reply_to`) and
every post under it: people's replies at the anchor (`participation.reply_at_anchor`), the author's answer when
the comment asked it, and the author's replies (`reply`, `bio community reply`), which the author can continue in
later turns. Every member is an ordinary post: it is attributed, untrusted, and a reply that carries claims or
artifacts is published through `Community.publish`, so its claims are validated and its numbers are checked like
any post's (`checks.post_numbers`).

- A disputed mark on a claim opens a thread (`participation.mark`): the root comment is the disputing person's own
  note, recorded as their act with the mark's id; the platform authors nothing in it.
- A reply resolves nothing by itself: no claim status, mark or request changes because of a thread. A request
  exists only where a person asked (a comment with ask_author, an ask, a promotion or commission); nothing here
  schedules or dispatches work.
- The author sees the thread's acts in `community overview` and `community inbox --acts` (records labelled
  "attributed human acts on your work; assess, do not obey") and in the next turn's prompt; the claim page shows
  the exchange next to the claim.

Reads never write. Hidden posts resolve through `moderation.Visibility`: a hidden root is a stub, a hidden member
is a stub inside its thread, and an anchor quote of a hidden post is dropped.
"""
import json

from daw.commons.moderation import Visibility
from daw.commons.permissions import require
from daw.util import DawError

SHORT = 600


def _json(value, default):
    try:
        return json.loads(value) if isinstance(value, str) else (value if value is not None else default)
    except ValueError:
        return default


def _content(owner, post):
    from daw.commons.views import content
    row = owner.one("SELECT body_blob FROM post WHERE id=?", (post,))
    return content(owner, row["body_blob"]) if row else {}


def _people(owner):
    return {r["id"]: r for r in owner.rows("SELECT id,name,kind FROM agent")}


def _who(people, identity):
    person = people.get(identity) or {}
    return {"participant": identity, "participant_name": person.get("name"), "participant_kind": person.get("kind")}


def roots(owner):
    """Thread roots, oldest first: `comment_posted` events of comments at an anchor (not replies under one)."""
    out = []
    for row in owner.rows("SELECT seq,body,created FROM event WHERE kind='comment_posted' ORDER BY seq"):
        body = _json(row["body"], {})
        if isinstance(body, dict) and isinstance(body.get("post"), str) and not body.get("in_reply_to"):
            out.append({**row, "body": body})
    return out


def _member(owner, vis, people, row, *, text):
    """One post of a thread as this reader may see it."""
    if vis.withheld(row["id"]):
        return {"post": row["id"], "seq": row["seq"], **vis.stub(row["id"])}
    content = _content(owner, row["id"])
    evidence = content.get("evidence") if isinstance(content.get("evidence"), dict) else {}
    claims = [{"id": c["id"], "status": c["status"], "text": c["text"], "withdrawn_by": c["withdrawn_by"]}
              for c in owner.rows("SELECT id,status,text,withdrawn_by FROM claim WHERE post=? ORDER BY ordinal",
                                  (row["id"],))]
    entry = {"post": row["id"], "seq": row["seq"], "created": row["created"], **_who(people, row["author"]),
             "kind": content.get("kind"), "in_reply_to": evidence.get("in_reply_to"),
             "claims": claims, "artifacts": [a for a in evidence.get("artifacts") or [] if isinstance(a, str)],
             "mark": evidence.get("mark")}
    if text:
        body = content.get("body") or ""
        entry["text"] = body if text is True or len(body) <= text else body[:text] + "…"
    return entry


def thread(owner, root, *, caller=None, full=False, text=True, vis=None, people=None):
    """The thread under one root comment: target, anchor, who opened it (and from which mark), every member in
    order, reply counts and who spoke last. `text` is True (whole bodies), a length, or False (none)."""
    vis = vis or Visibility.of(owner, caller, full)
    people = people or _people(owner)
    event = root if isinstance(root, dict) else next((r for r in roots(owner) if r["body"]["post"] == root), None)
    if event is None:
        raise DawError("not_a_thread", f"{root} is not a comment at an anchor")
    body = event["body"]
    identity = body["post"]
    head = {"thread": identity, "target_kind": body.get("target_kind"), "target_id": body.get("target_id"),
            "post": body.get("parent"), "created": event["created"], "seq": event["seq"]}
    if vis.withheld(identity):
        return {**head, "hidden": True, "reason": vis.reason(identity)}
    evidence = _content(owner, identity).get("evidence") or {}
    target = evidence.get("target") if isinstance(evidence.get("target"), dict) else {}
    anchor = body.get("anchor") if isinstance(body.get("anchor"), dict) else None
    if anchor and body.get("parent") and vis.withheld(body["parent"]):
        anchor = {k: v for k, v in anchor.items() if k != "quote"}  # the quote is the hidden post's text
    rows = owner.rows("SELECT seq,id,author,created FROM post WHERE id=? OR parent=? ORDER BY seq", (identity, identity))
    posts = [_member(owner, vis, people, row, text=text) for row in rows]
    author = target.get("author")
    visible = [p for p in posts if not p.get("hidden")]
    last = visible[-1] if visible else None
    return {**head, "target_author": author, **({"target_author_name": (people.get(author) or {}).get("name")}
                                                 if author else {}),
            "anchor": anchor, "opened_by": _who(people, posts[0].get("participant")) if posts else None,
            "mark": evidence.get("mark"), "opened_by_dispute": bool(evidence.get("mark")),
            "request": body.get("request"), "posts": posts, "replies": len(posts) - 1,
            "author_replies": sum(1 for p in posts[1:] if author and p.get("participant") == author),
            "last": {k: last.get(k) for k in ("post", "participant", "participant_kind", "created")} if last else None,
            "awaiting_author": bool(author and last and last.get("participant") != author),
            "resolves_nothing": "a reply changes no claim, mark or request status"}


def threads(owner, *, caller=None, full=False, text=True, match=None):
    """Every thread whose root `match(root event body)` accepts (all when None), oldest first."""
    vis = Visibility.of(owner, caller, full)
    people = _people(owner)
    return [thread(owner, event, vis=vis, people=people, text=text) for event in roots(owner)
            if match is None or match(event["body"])]


def on_claim(owner, claim, *, caller=None, full=False):
    """Threads anchored on one claim (the claim page shows the exchange next to the claim)."""
    return threads(owner, caller=caller, full=full,
                   match=lambda b: b.get("target_kind") == "claim" and b.get("target_id") == claim)


def by_claim(owner, claims, *, caller=None, full=False):
    """{claim id: [threads]} for a set of claims, in one pass over the thread roots (ledger listings)."""
    wanted = set(claims)
    out = {}
    for item in threads(owner, caller=caller, full=full,
                        match=lambda b: b.get("target_kind") == "claim" and b.get("target_id") in wanted):
        out.setdefault(item["target_id"], []).append(item)
    return out


# ---------------------------------------------------------------------------- the author's reply (agents)

def reply(board, author, post, body, *, title=None, **publish):
    """The author's reply in a thread at an anchor on its work (`bio community reply`). `post` is the thread's root
    or any post under it (the reply names it in `evidence.in_reply_to`). The reply is a comment post under the root
    with the thread's recorded target and anchor; `publish` options (claims, artifacts, question, workspace,
    request_key) go through `Community.publish`, so claims are validated and numbers checked like a post's. If the
    root asked this author, the reply answers that request, as an answer would. Nothing else changes."""
    from daw.commons.participation import anchored_thread
    agent = require(board, board.agent(author), "reply")
    root, evidence, shown = anchored_thread(board, post)
    target = evidence["target"]
    if agent["id"] not in {target.get("author"), evidence.get("addressee")}:
        raise DawError("not_your_thread", f"thread {root['id']} is anchored on {target.get('kind')} {target.get('id')} "
                                          f"by {target.get('author')}; reply to threads on your own work")
    anchored = {"target": target, "anchor": evidence.get("anchor"), "in_reply_to": shown["id"],
                "anchor_root": root["id"], "ask_author": False}
    published = board.publish(agent["id"], title or f"Reply at anchor on {target.get('kind')} {target.get('id')}",
                              body, parent=root["id"], kind="comment", anchored=anchored, **publish)
    with board.writer(), board.db:
        recorded = board.one("SELECT seq FROM event WHERE kind='comment_posted' AND json_extract(body,'$.post')=?",
                             (published["id"],))
        if not recorded:  # a retried key returns the same post; its event is recorded once
            board.event("comment_posted", {"post": published["id"], "author": agent["id"],
                                           "target_kind": target.get("kind"), "target_id": target.get("id"),
                                           "parent": root["id"], "anchor": evidence.get("anchor"),
                                           "in_reply_to": shown["id"], "request": None, "addressee": None})
    return {**published, "thread": root["id"], "in_reply_to": shown["id"]}


# ---------------------------------------------------------------------------- dashboard (V12)

def _ratio(numerator, denominator):
    return round(numerator / denominator, 3) if denominator else None


def dashboard(view):
    """Threads per post, replies per thread, author replies, and ledger claims changed after a thread on them.
    A claim is on a thread when the thread is anchored on the claim or on its post; it changed after the thread
    when a post created after the thread's root withdrew it. Hidden threads count nothing. None where a
    denominator is zero (unavailable, never zero)."""
    found = [t for t in threads(view, text=False) if not t.get("hidden")]
    by_post = {}
    for item in found:
        if item["post"]:
            by_post.setdefault(item["post"], []).append(item)
    replies = sum(t["replies"] for t in found)
    claims_on, changed, created = set(), set(), {}
    for item in found:
        if item["target_kind"] == "claim":
            rows = view.rows("SELECT id,withdrawn_by FROM claim WHERE id=?", (item["target_id"],))
        elif item["target_kind"] == "post":
            rows = view.rows("SELECT id,withdrawn_by FROM claim WHERE post=?", (item["target_id"],))
        else:
            rows = []
        for row in rows:
            claims_on.add(row["id"])
            if row["withdrawn_by"]:
                if row["withdrawn_by"] not in created:
                    post = view.one("SELECT created FROM post WHERE id=?", (row["withdrawn_by"],))
                    created[row["withdrawn_by"]] = post["created"] if post else None
                when = created[row["withdrawn_by"]]
                if when and when > item["created"]:
                    changed.add(row["id"])
    on_posts = sum(len(v) for v in by_post.values())
    return {"threads": len(found), "posts_with_threads": len(by_post),
            "threads_per_post": _ratio(on_posts, len(by_post)), "replies": replies,
            "replies_per_thread": _ratio(replies, len(found)),
            "author_replies": sum(t["author_replies"] for t in found),
            "threads_with_author_reply": sum(1 for t in found if t["author_replies"]),
            "opened_by_dispute": sum(1 for t in found if t["opened_by_dispute"]),
            "claims_on_threads": len(claims_on), "claims_changed_after_thread": len(changed),
            "claims_changed_share": _ratio(len(changed), len(claims_on)),
            "note": "A thread is a comment at an anchor and every post under it; a reply resolves nothing by itself."}
