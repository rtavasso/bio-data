"""Per-commons read policy (spec v2 V9): public, members or private, enforced by the server for every request.

The policy is the operator's, in `<commons>/commons.toml` (a multi-tenant host may override it per tenant in
`tenants.toml`):

    [access]
    read = "members"     # public (default) | members | private

- **public**: anonymous reads, as before (M7.2).
- **members**: any authenticated participant (a bearer token or a session cookie of this commons).
- **private**: operators, and participants an operator explicitly granted membership
  (`bio commons member grant NAME`, `POST /api/members`); a revocation ends access at the next request,
  and an open response such as an event stream within `RECHECK_SECONDS`.

Enforcement is one ASGI middleware inside each commons application (`ReadPolicy`), so every route of every
router, including routes added later, is covered: posts, threads, the map, SSE (`/api/events`, the inbox
stream), blobs, artifact bytes, uploads, exports, federation, search and the dashboard. Only these answer
without membership: `POST|DELETE /api/session` (logging in and out), `GET /api/health` (reduced to liveness
and the policy), `GET /api/access` (the policy and the caller's standing) and, for an authenticated caller
who is not a member, `GET /api/me` (so the web app can say so). The web app's HTML and static assets carry no
board content and are served as usual; every byte of board content comes from `/api/`.

Local mode (`bio commons serve`, loopback, one local person) is unaffected: there is nobody else to keep out.

Membership is a projection (`membership`) of `member_granted` / `member_revoked` board events, rebuilt by
`rebuild`. Grants and revocations are operator writes (permission `participants`) through the write path.
"""
import json
import time
import tomllib
from pathlib import Path

from daw.commons.permissions import require
from daw.util import DawError, now

POLICIES = ("public", "members", "private")
DEFAULT = "public"
RECHECK_SECONDS = 5.0
OPEN = {("POST", "/api/session"), ("DELETE", "/api/session"), ("GET", "/api/health"), ("HEAD", "/api/health"),
        ("GET", "/api/access"), ("POST", "/api/visitors")}  # visitor sign-in refuses itself off a public commons
SELF = {("GET", "/api/me")}
EVENTS = {"member_granted": "member", "member_revoked": "revoked"}
NOTES = {"public": "anyone may read", "members": "any logged-in participant may read",
         "private": "operators and granted members may read", "local": "single local person (loopback)"}


def policy(root, override=None):
    """The commons' read policy: `override` (a tenant's), else `commons.toml [access] read`, else public."""
    if override is not None:
        value = override
    else:
        path = Path(root) / "commons.toml"
        configured = {}
        if path.is_file():
            try:
                configured = tomllib.loads(path.read_text()).get("access", {})
            except tomllib.TOMLDecodeError as e:
                raise DawError("invalid_commons_config", str(e)) from e
        if not isinstance(configured, dict) or set(configured) - {"read"}:
            raise DawError("invalid_commons_config", "[access] takes read = public | members | private")
        value = configured.get("read", DEFAULT)
    if value not in POLICIES:
        raise DawError("invalid_commons_config", f"access read must be one of {', '.join(POLICIES)}, not {value!r}")
    return value


# ---------------------------------------------------------------------------- membership (operators)

def is_member(owner, participant):
    """True for operators and for participants with a current grant. Works on Community and Archive."""
    if not participant:
        return False
    if participant.get("kind") == "operator":
        return True
    row = owner.one("SELECT state FROM membership WHERE participant=?", (participant["id"],))
    return bool(row and row["state"] == "member")


def _upsert(board, participant, state, actor, reason, seq, updated):
    board.db.execute("INSERT INTO membership(participant,state,actor,reason,event_seq,updated) VALUES(?,?,?,?,?,?) "
                     "ON CONFLICT(participant) DO UPDATE SET state=excluded.state,actor=excluded.actor,"
                     "reason=excluded.reason,event_seq=excluded.event_seq,updated=excluded.updated",
                     (participant, state, actor, reason, seq, updated))


def _change(board, actor, participant, reason, event):
    operator = require(board, board.agent(actor), "participants")
    subject = board.agent(participant)
    if subject["kind"] == "agent":
        raise DawError("agents_use_the_cli", "agents read the board through bio community in their checkout")
    reason = (reason or "").strip()
    if len(reason) > 2000:
        raise DawError("invalid_reason", "at most 2000 characters")
    state = EVENTS[event]
    with board.writer(), board.db:
        current = board.one("SELECT state FROM membership WHERE participant=?", (subject["id"],))
        if (current["state"] if current else "revoked") == state:
            raise DawError("membership_unchanged", f"{subject['name']} is already {state}")
        board.event(event, {"participant": subject["id"], "actor": operator["id"], "reason": reason})
        seq = board.db.execute("SELECT max(seq) FROM event").fetchone()[0]
        _upsert(board, subject["id"], state, operator["id"], reason, seq, now())
    return membership(board, subject["id"])


def grant(board, actor, participant, reason=""):
    return _change(board, actor, participant, reason, "member_granted")


def revoke(board, actor, participant, reason=""):
    return _change(board, actor, participant, reason, "member_revoked")


def membership(owner, participant):
    return owner.one("SELECT m.*,a.name,a.kind FROM membership m JOIN agent a ON a.id=m.participant "
                     "WHERE m.participant=?", (participant,))


def members(owner):
    return owner.rows("SELECT m.*,a.name,a.kind FROM membership m JOIN agent a ON a.id=m.participant "
                      "ORDER BY m.updated,m.participant")


def rebuild(board):
    """Recreate the membership projection from immutable events; returns the number of rows."""
    with board.writer(), board.db:
        board.db.execute("DELETE FROM membership")
        for row in board.rows("SELECT seq,kind,body,created FROM event WHERE kind IN ('member_granted','member_revoked') "
                              "ORDER BY seq"):
            body = json.loads(row["body"])
            _upsert(board, body["participant"], EVENTS[row["kind"]], body["actor"], body.get("reason", ""),
                    row["seq"], row["created"])
    return board.db.execute("SELECT count(*) FROM membership").fetchone()[0]


# ---------------------------------------------------------------------------- decisions

def decide(owner, read_policy, participant):
    """(allowed, error reason) for one caller (None when unauthenticated)."""
    if read_policy == "public":
        return True, None
    if participant is None:
        return False, "authentication_required"
    if read_policy == "members" or is_member(owner, participant):
        return True, None
    return False, "not_a_member"


def standing(owner, settings, participant):
    """What `GET /api/access` tells a caller: the policy and whether they may read."""
    local = settings.mode == "local"
    read = "local" if local else settings.access
    allowed, reason = (True, None) if local else decide(owner, settings.access, participant)
    from daw.commons import visitors
    return {"mode": settings.mode, "read": read, "authenticated": participant is not None,
            "participant": participant["id"] if participant else None, "member": allowed, "reason": reason,
            "visitor_signin": visitors.enabled(settings), "note": NOTES[read]}


def route_path(scope):
    """The request path inside this application (a host mounts each tenant under /c/<tenant>)."""
    path, root = scope.get("path", ""), scope.get("root_path", "")
    return path[len(root):] if root and path.startswith(root) else path


def caller(scope, view):
    """The authenticated participant of a request (None when it presents no valid credential)."""
    from starlette.requests import Request

    from daw.commons import auth
    try:
        return auth.authenticate(Request(scope), view)
    except DawError as error:
        if error.reason != "authentication_required":
            raise
        return None


def check(scope, settings):
    """(allowed, status, error body) for a request under the commons' read policy. Read-only."""
    from daw.commons.archive import Archive
    with Archive(settings.root) as view:
        participant = caller(scope, view)
        allowed, reason = decide(view, settings.access, participant)
    if allowed or (reason == "not_a_member" and (scope["method"], route_path(scope)) in SELF):
        return True, 200, None
    status = 401 if reason == "authentication_required" else 403
    detail = ("this commons is readable by its members only; log in with a token at POST /api/session"
              if reason == "authentication_required" else
              "this commons is private; an operator grants membership (bio commons member grant)")
    return False, status, {"error": reason, "detail": detail, "read_policy": settings.access}


class ReadPolicy:
    """ASGI middleware enforcing the read policy on every /api request (see the module docstring)."""

    def __init__(self, app, settings, recheck_seconds=RECHECK_SECONDS):
        self.app, self.settings, self.recheck = app, settings, recheck_seconds

    async def __call__(self, scope, receive, send):
        settings = self.settings
        if scope["type"] != "http" or settings.mode == "local" or settings.access == "public":
            return await self.app(scope, receive, send)
        path = route_path(scope)
        if not path.startswith("/api/") or (scope["method"], path) in OPEN:
            return await self.app(scope, receive, send)
        from anyio import to_thread
        allowed, status, error = await to_thread.run_sync(check, scope, settings)
        if not allowed:
            body = json.dumps(error).encode()
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": body})
            return
        state = {"closed": False, "checked": time.monotonic()}

        async def guarded_receive():
            if state["closed"]:
                return {"type": "http.disconnect"}
            return await receive()

        async def guarded_send(message):
            if state["closed"]:
                return
            if message["type"] == "http.response.body" and message.get("more_body") \
                    and time.monotonic() - state["checked"] >= self.recheck:
                state["checked"] = time.monotonic()
                still, _, _ = await to_thread.run_sync(check, scope, settings)
                if not still:
                    # Access ended (token or membership revoked): end a long response such as an event stream.
                    state["closed"] = True
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                    return
            await send(message)

        await self.app(scope, guarded_receive, guarded_send)
