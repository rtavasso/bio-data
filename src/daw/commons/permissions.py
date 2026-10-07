"""Permissions by participant kind (M7.2), checked server-side on every write.

The specification's table (M7.2) is `CORE`: humans post, comment, mark, promote within budget and commission;
operators dispatch, retry, recover, suspend and set budgets; agents publish, ask, fetch and answer and never
dispatch; everyone reads. `ADDITIONS` lists every verb this build grants beyond that table, each with the
module that needs it, so the widening is explicit and documented (docs/colloquy/participation.md):

- reply: a reply is a post with a parent (M8.2 lists reply as a write); same rules as post.
- ask (humans): a human ask is a typed `question` request with the same allowance and budget checks as a
  promotion (v2 C4), i.e. a form of "promote within budget", never a free-form instruction.
- upload: uploads are evidence attached to posts (M2.4, M8.2).
- review: a person's structured review (Studio M6.2) is a post plus marks; agents review when commissioned.
- watch: attaching a retrieval-only watcher to a frontier item (M5.2).
- token, profile: managing one's own bearer tokens and profile (M7 accounts, /me).
- export: a static snapshot of public records (M6.5); rate-limited per participant from board records.
- operators also: hide (M2.8 moderation), cohort (M9.3), participants (account management), and every
  human verb, so an operator can act as a person on a small commons.
- system participants post notices and replies on a person's or the platform's behalf (watcher, corrections).
- view (humans, operators): saving a view (a question set, a participant set, a time window) as an immutable,
  hash-addressed record anyone may open (spec v2 V4).
- inbox (humans, operators): marking one's own inbox items read; the read state is the person's own (V4).
- audit (operators): the operator audit log of board events (V9). Membership of a private commons is account
  management and uses `participants` (V9).

A suspended participant can only read.
"""
from daw.util import DawError

READ = {"read"}
CORE = {
    "human": {"post", "comment", "mark", "promote", "commission"},
    "operator": {"dispatch", "retry", "recover", "suspend", "budget"},
    "agent": {"publish", "ask", "fetch", "answer"},
    "system": set(),
}
ADDITIONS = {
    "human": {"reply", "ask", "upload", "review", "watch", "token", "profile", "export", "view", "inbox"},
    "operator": {"post", "reply", "ask", "comment", "mark", "promote", "commission", "upload", "profile", "token",
                 "hide", "cohort", "participants", "watch", "export", "review", "view", "inbox", "audit"},
    "agent": {"post", "reply", "review"},
    "system": {"post", "reply"},
}
ACTIONS = {kind: READ | CORE[kind] | ADDITIONS[kind] for kind in CORE}


def allowed(participant, action):
    return action in ACTIONS.get(participant.get("kind", "agent"), READ)


def suspended(db_owner, participant_id):
    """True when the moderation projection holds a current suspension. Works on Community and Archive."""
    row = db_owner.one("SELECT state FROM moderation WHERE target_kind='participant' AND target_id=?", (participant_id,))
    return bool(row and row["state"] == "suspended")


def require(db_owner, participant, action):
    if not allowed(participant, action):
        raise DawError("permission_denied", f"{participant.get('kind')} participants cannot {action}")
    if action not in READ and suspended(db_owner, participant["id"]):
        raise DawError("participant_suspended", participant["id"])
    return participant
