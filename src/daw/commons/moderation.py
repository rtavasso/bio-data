"""Moderation (M2.8): reversible hide flags, participant suspension and human rate limits.

Every action is one board event (`post_hidden`, `post_unhidden`, `participant_suspended`,
`participant_reinstated`) plus an upsert of the `moderation` projection, which
`rebuild` recreates from those events alone. Nothing here deletes or rewrites bytes:
a hidden post stays in the archive, readable through its identifier, with the
moderation record shown beside it. Only operators moderate.

Rate limits apply to human accounts and are computed from the board's own records
(posts, marks and uploads created in the last hour), so they survive restarts and
hold across processes. Operator-tunable limits live in `<commons>/commons.toml`:

    [limits]
    posts_per_hour = 30     # posts, comments, questions, promotions and commissions
    marks_per_hour = 60
    uploads_per_hour = 20
    upload_bytes = 26214400 # 25 MiB per file
"""
import threading
import tomllib
from datetime import UTC, datetime, timedelta

from daw.commons.permissions import require
from daw.util import DawError, now

DEFAULT_LIMITS = {"posts_per_hour": 30, "marks_per_hour": 60, "uploads_per_hour": 20, "upload_bytes": 25 * 1024 * 1024}
ACTIONS = {
    "hide": ("post", "hidden", "post_hidden", "hide"),
    "unhide": ("post", "visible", "post_unhidden", "hide"),
    "suspend": ("participant", "suspended", "participant_suspended", "suspend"),
    "reinstate": ("participant", "active", "participant_reinstated", "suspend"),
}
EVENTS = {event: (kind, state) for kind, state, event, _ in ACTIONS.values()}
# What each rate limit counts: (table, author column).
COUNTED = {"posts_per_hour": ("post", "author"), "marks_per_hour": ("mark", "participant"),
           "uploads_per_hour": ("upload", "uploader")}


def limits(root):
    """Operator-set limits from commons.toml [limits]; unknown keys and non-positive values are refused."""
    path = root / "commons.toml"
    configured = {}
    if path.is_file():
        try:
            configured = tomllib.loads(path.read_text()).get("limits", {})
        except tomllib.TOMLDecodeError as e:
            raise DawError("invalid_commons_config", str(e)) from e
    unknown = set(configured) - set(DEFAULT_LIMITS)
    if unknown:
        raise DawError("invalid_commons_config", f"unknown limits {', '.join(sorted(unknown))}")
    for key, value in configured.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise DawError("invalid_commons_config", f"{key} must be a positive integer")
    return {**DEFAULT_LIMITS, **configured}


def check_rate(board, participant, limit):
    """Raise rate_limited when a human already made `limit` writes of this family in the last hour."""
    if participant.get("kind") != "human":
        return
    allowed = limits(board.root)[limit]
    table, column = COUNTED[limit]
    since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    count = board.db.execute(f"SELECT count(*) FROM {table} WHERE {column}=? AND created>?",
                             (participant["id"], since)).fetchone()[0]
    if count >= allowed:
        raise DawError("rate_limited", f"{limit.replace('_', ' ')} limit is {allowed}; try again later")


def state(db_owner, target_kind, target_id):
    """Current moderation row (or None). Works on Community and Archive."""
    return db_owner.one("SELECT * FROM moderation WHERE target_kind=? AND target_id=?", (target_kind, target_id))


def hidden(db_owner, post):
    row = state(db_owner, "post", post)
    return bool(row and row["state"] == "hidden")


def _upsert(board, kind, target, value, actor, reason, seq, updated):
    board.db.execute("INSERT INTO moderation(target_kind,target_id,state,actor,reason,event_seq,updated) "
                     "VALUES(?,?,?,?,?,?,?) ON CONFLICT(target_kind,target_id) DO UPDATE SET state=excluded.state,"
                     "actor=excluded.actor,reason=excluded.reason,event_seq=excluded.event_seq,updated=excluded.updated",
                     (kind, target, value, actor, reason, seq, updated))


def moderate(board, actor, action, target, reason):
    """Apply one moderation action. Operator only; the reason is part of the public record."""
    if action not in ACTIONS:
        raise DawError("unknown_moderation_action", action)
    kind, value, event, permission = ACTIONS[action]
    operator = require(board, board.agent(actor), permission)
    reason = (reason or "").strip()
    if not reason or len(reason) > 2000:
        raise DawError("moderation_reason_required", "a reason (at most 2000 characters) is recorded publicly")
    if kind == "post":
        target = board.show(target)["id"]
    else:
        subject = board.agent(target)
        if subject["id"] == operator["id"] or subject["kind"] == "operator":
            raise DawError("cannot_suspend_operator", "operators are managed outside the board")
        target = subject["id"]
    with board.writer(), board.db:
        current = state(board, kind, target)
        default = "visible" if kind == "post" else "active"
        if (current["state"] if current else default) == value:
            raise DawError("moderation_state_unchanged", f"{kind} {target} is already {value}")
        board.event(event, {"target_kind": kind, "target_id": target, "actor": operator["id"], "reason": reason})
        seq = board.db.execute("SELECT max(seq) FROM event").fetchone()[0]
        _upsert(board, kind, target, value, operator["id"], reason, seq, now())
    return state(board, kind, target)


def hide(board, actor, post, reason):
    return moderate(board, actor, "hide", post, reason)


def unhide(board, actor, post, reason):
    return moderate(board, actor, "unhide", post, reason)


def suspend(board, actor, participant, reason):
    return moderate(board, actor, "suspend", participant, reason)


def reinstate(board, actor, participant, reason):
    return moderate(board, actor, "reinstate", participant, reason)


def rebuild(board):
    """Recreate the moderation projection from immutable events; returns the number of rows."""
    import json
    with board.writer(), board.db:
        board.db.execute("DELETE FROM moderation")
        for row in board.rows("SELECT seq,kind,body,created FROM event WHERE kind IN (%s) ORDER BY seq"
                              % ",".join("?" * len(EVENTS)), tuple(EVENTS)):
            body = json.loads(row["body"])
            kind, value = EVENTS[row["kind"]]
            _upsert(board, kind, body["target_id"], value, body["actor"], body["reason"], row["seq"], row["created"])
    return board.db.execute("SELECT count(*) FROM moderation").fetchone()[0]


# ---------------------------------------------------------------------------- visibility (C2)

# Fields that carry post text (or text quoted from a post) wherever they appear in a record or event body.
TEXT_FIELDS = frozenset({"title", "body", "snippet", "excerpt", "summary", "quote", "text", "note", "content",
                         "context", "request_title", "post_title", "replacement_title", "label"})


class Visibility:
    """The one moderation rule every reader applies (M2.8, M7.3, spec v2 C2).

    A hidden post is withheld at display level; its bytes stay in the archive. A reader gets
    `{"id": ..., "hidden": true, "reason": ...}` for it and nothing else: no title, body, excerpt, author,
    kind, evidence, claims or anchor quotes of its text. Only a caller holding `hide` (an operator who is
    not suspended) who asks for `full` sees the content, still labelled hidden with the moderation record.
    Every read model (views, evidence map, timelines, question pages, claims, Studio, dashboard, search),
    the SSE framing and export resolve visibility here. Built per request from the moderation projection.
    """

    def __init__(self, records=None, *, reveal=False, blobs=None, refused=None):
        self.records = dict(records or {})
        self.reveal = bool(reveal)
        self.blobs = dict(blobs or {})
        # Write-ups the number checker refused (spec v2 C5): {post: verdict summary}, or a loader called on first
        # use (the checker itself reads claims through a Visibility, so loading is lazy and never re-entered).
        self._refused = refused

    @classmethod
    def of(cls, owner, caller=None, full=False):
        """Visibility for one reader of a Community or Archive. `full` needs the `hide` permission."""
        from daw.commons.permissions import allowed, suspended
        reveal = bool(full and caller and allowed(caller, "hide") and not suspended(owner, caller["id"]))
        records, blobs = {}, {}
        for row in owner.rows("SELECT m.target_id,m.reason,m.actor,m.updated,m.event_seq,p.body_blob FROM moderation m "
                              "LEFT JOIN post p ON p.id=m.target_id WHERE m.target_kind='post' AND m.state='hidden' "
                              "ORDER BY m.target_id"):
            records[row["target_id"]] = {"reason": row["reason"], "actor": row["actor"], "updated": row["updated"],
                                         "event_seq": row["event_seq"]}
            if row["body_blob"]:
                blobs[row["body_blob"]] = row["target_id"]
        return cls(records, reveal=reveal, blobs=blobs, refused=lambda: _refused_writeups(owner))

    # -------------------------------------------------------------- write-ups refused by the number checker (C5)
    @property
    def refused_writeups(self):
        if callable(self._refused):
            loader, self._refused = self._refused, {}  # a re-entrant read during loading sees none
            self._refused = loader()
        return self._refused or {}

    def refused(self, post):
        """True when this caller sees the post as a refused write-up's placeholder (hidden posts stay stubs)."""
        return not self.reveal and post not in self.records and post in self.refused_writeups

    def placeholder(self, post, card):
        """A refused write-up as readers see it: identity and structure, the placeholder title and snippet."""
        from daw.commons.checks import PLACEHOLDER_TITLE, snippet
        info = self.refused_writeups[post]
        return {**card, "title": PLACEHOLDER_TITLE, **({"snippet": snippet(info)} if "snippet" in card else {}),
                "withheld": info}

    # -------------------------------------------------------------- posts
    def hidden(self, post):
        """True when the post carries a current hide flag (whether or not this caller may read it)."""
        return post in self.records

    def withheld(self, post):
        """True when this caller must not see the post's content."""
        return post in self.records and not self.reveal

    def reason(self, post):
        record = self.records.get(post)
        return record["reason"] if record else None

    def key(self):
        """Cache-key component: the hidden set and whether this caller reads through it."""
        return {"hidden": sorted(self.records), "reveal": self.reveal, "refused": sorted(self.refused_writeups)}

    def stub(self, post, **structure):
        """The whole of what a reader learns about a hidden post (plus caller-supplied structural keys,
        such as the nested children of a thread node, which are other posts' own cards)."""
        return {"id": post, "hidden": True, "reason": self.reason(post), **structure}

    def card(self, post, card, *, keep=()):
        """A post-shaped record as this caller may see it."""
        if self.withheld(post):
            return self.stub(post, **{k: card[k] for k in keep if k in card})
        if post in self.records:
            return {**card, "id": post, "hidden": True, "reason": self.reason(post),
                    "moderation": self.records[post], "revealed": True}
        if self.refused(post):
            return {**self.placeholder(post, card), "hidden": False}
        return {**card, "hidden": False}

    def title(self, post, title):
        if self.withheld(post):
            return None
        if self.refused(post):
            from daw.commons.checks import PLACEHOLDER_TITLE
            return PLACEHOLDER_TITLE
        return title

    # -------------------------------------------------------------- quoted text
    def anchor(self, anchor, target=None):
        """A comment anchor without its quote when the anchored post (by id or body blob) is withheld."""
        if not isinstance(anchor, dict) or self.reveal or not self.records:
            return anchor
        target_id = target.get("id") if isinstance(target, dict) else target
        if (isinstance(target_id, str) and target_id in self.records) or anchor.get("blob") in self.blobs:
            return {**{k: v for k, v in anchor.items() if k != "quote"}, "quote": None, "quote_withheld": True}
        return anchor

    def evidence(self, evidence):
        """Post evidence with any anchor quote of a withheld post removed."""
        if not isinstance(evidence, dict) or "anchor" not in evidence:
            return evidence
        return {**evidence, "anchor": self.anchor(evidence["anchor"], evidence.get("target"))}

    def touches(self, value):
        """True when a record mentions a withheld post by id or by body blob anywhere inside it."""
        if self.reveal or not self.records:
            return False
        if isinstance(value, str):
            return value in self.records or value in self.blobs
        if isinstance(value, dict):
            return any(self.touches(v) for v in value.values())
        if isinstance(value, (list, tuple)):
            return any(self.touches(v) for v in value)
        return False

    def scrub(self, value):
        """Remove every text field (titles, bodies, excerpts, quotes, notes) from a record, keeping identities."""
        if isinstance(value, dict):
            return {k: (None if k in TEXT_FIELDS and isinstance(v, str) else self.scrub(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        return value

    def event(self, event):
        """A board event as framed for SSE and the JSON log: an event that mentions a withheld post keeps its
        identities but loses every text field (anchor quotes, titles, excerpts). Moderation events keep their
        public reason. Applied at frame time, so a backlog replayed after a hide is redacted too."""
        body = event.get("body")
        if event.get("kind") in EVENTS or not isinstance(body, dict) or not self.touches(body):
            return event
        return {**event, "body": self.scrub(body), "redacted": "mentions a post hidden by moderation"}

    # -------------------------------------------------------------- claims
    def claim(self, row):
        """A claim of a withheld post is the post's content: readers get its id, its post and the reason."""
        post = row.get("post")
        if self.withheld(post):
            return {"id": row.get("id"), "post": post, "hidden": True, "reason": self.reason(post)}
        return row


_LOADING = threading.local()


def _refused_writeups(owner):
    """{post: verdict summary} of refused write-ups: recorded `writeup_check` verdicts on any board owner; on a
    read-only Archive also write-ups without a record, checked now (daw.commons.checks.withheld)."""
    from daw.commons.archive import Archive
    if getattr(_LOADING, "active", False):
        return {}  # the checker reads posts and claims through a Visibility while computing verdicts
    if isinstance(owner, Archive):
        from daw.commons.checks import withheld
        _LOADING.active = True
        try:
            return withheld(owner)
        finally:
            _LOADING.active = False
    import json
    latest = {}
    for row in owner.rows("SELECT seq,body FROM event WHERE kind='writeup_check' ORDER BY seq"):
        body = json.loads(row["body"])
        latest[body["post"]] = {"status": body["status"], "source": "recorded",
                                "problems": len(body.get("problems") or []), "seq": row["seq"]}
    return {post: info for post, info in latest.items() if info["status"] == "refused"}


def visibility(owner, caller=None, full=False):
    """Shorthand for `Visibility.of`."""
    return Visibility.of(owner, caller, full)
