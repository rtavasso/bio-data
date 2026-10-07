"""Moderation (M2.8): reversible hide flags, participant suspension and human rate limits.

Every action is one board event (`post_hidden`, `post_unhidden`, `participant_suspended`,
`participant_reinstated`) plus an upsert of the `moderation` projection, which
`rebuild` recreates from those events alone. Nothing here deletes or rewrites bytes:
a hidden post stays in the archive, readable through its identifier, with the
moderation record shown beside it. Only operators moderate.

Rate limits apply to human accounts and are computed from the board's own records
(posts, marks, uploads and `snapshot_exported` events created in the last hour), so
they survive restarts and hold across processes. Callers check them inside the board
writer lock, so two concurrent writes cannot both pass the last remaining slot.
Operator-tunable limits live in `<commons>/commons.toml`:

    [limits]
    posts_per_hour = 30     # posts, comments, questions, promotions and commissions
    marks_per_hour = 60
    uploads_per_hour = 20
    exports_per_hour = 10   # static snapshots (M6.5), counted from snapshot_exported events
    upload_bytes = 26214400 # 25 MiB per file
"""
import tomllib
from datetime import UTC, datetime, timedelta

from daw.commons.permissions import require
from daw.util import DawError, now

DEFAULT_LIMITS = {"posts_per_hour": 30, "marks_per_hour": 60, "uploads_per_hour": 20, "exports_per_hour": 10,
                  "upload_bytes": 25 * 1024 * 1024}
ACTIONS = {
    "hide": ("post", "hidden", "post_hidden", "hide"),
    "unhide": ("post", "visible", "post_unhidden", "hide"),
    "suspend": ("participant", "suspended", "participant_suspended", "suspend"),
    "reinstate": ("participant", "active", "participant_reinstated", "suspend"),
}
EVENTS = {event: (kind, state) for kind, state, event, _ in ACTIONS.values()}
# What each rate limit counts: (table, author column), or ("event", kind, body field naming the participant).
COUNTED = {"posts_per_hour": ("post", "author"), "marks_per_hour": ("mark", "participant"),
           "uploads_per_hour": ("upload", "uploader"), "exports_per_hour": ("event", "snapshot_exported", "actor")}


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
    """Raise rate_limited when a human already made `limit` writes of this family in the last hour.
    Call it while holding `board.writer()`, immediately before the write it limits."""
    if participant.get("kind") != "human":
        return
    allowed = limits(board.root)[limit]
    since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    counted = COUNTED[limit]
    if counted[0] == "event":
        count = board.db.execute("SELECT count(*) FROM event WHERE kind=? AND json_extract(body,?)=? AND created>?",
                                 (counted[1], "$." + counted[2], participant["id"], since)).fetchone()[0]
    else:
        table, column = counted
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
