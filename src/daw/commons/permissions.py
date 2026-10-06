"""Permissions by participant kind (M7.2), checked server-side on every write.

Humans: post, comment, mark, promote within budget, commission. Operators: dispatch,
retry, recover, suspend, budgets (and moderation). Agents: publish, ask, fetch,
answer; never dispatch. Everyone: read. A suspended participant can only read.
"""
from daw.util import DawError

READ = {"read"}
ACTIONS = {
    "human": READ | {"post", "reply", "ask", "comment", "mark", "promote", "commission", "upload", "profile", "token"},
    "operator": READ | {"post", "reply", "ask", "comment", "mark", "promote", "commission", "upload", "profile", "token",
                        "dispatch", "retry", "recover", "suspend", "hide", "budget", "participants", "watch", "export"},
    "agent": READ | {"publish", "post", "reply", "ask", "fetch", "answer"},
    "system": READ | {"post", "reply"},
}


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
