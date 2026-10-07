"""Caller identity for HTTP requests (M7).

Local single-user mode skips login: every request acts as one human participant
(created on first start), or one operator with `serve --as-operator`. Accounts
mode accepts `Authorization: Bearer <token>` for integrations or the signed
session cookie set by POST /api/session (see
`daw.commons.accounts`). Agents never reach the HTTP write API: they use the bio
CLI in their checkout.

Writes authenticated by a cookie, and every write in local mode, must carry the
`X-Colloquy-Request: 1` header. Browsers cannot add a custom header cross-origin
without a CORS preflight this app never grants, so another site cannot forge a
write with the person's cookie (or against a loopback server). Bearer requests
are exempt: browsers never attach bearer tokens on their own.
"""
from daw.commons.participants import add_participant
from daw.util import DawError

CSRF_HEADER = "X-Colloquy-Request"
WRITERS = ("human", "operator")


def prepare(board, settings):
    if settings.mode == "local":
        row = board.one("SELECT id,kind FROM agent WHERE name=?", (settings.local_user,))
        kind = "operator" if settings.local_operator else "human"
        if row is None:
            add_participant(board, settings.local_user, kind, profile={"display_name": settings.local_user})
        elif row["kind"] not in {"human", "operator"}:
            raise DawError("local_user_must_be_human", settings.local_user)
        elif settings.local_operator and row["kind"] != "operator":
            # A participant's kind never changes: name a new local operator instead.
            raise DawError("local_user_not_operator", f"{settings.local_user} is a {row['kind']}; "
                                                      "serve --as-operator with another --user name")
    else:
        from daw.commons.accounts import session_key
        session_key(settings.root)


def authenticate(request, archive):
    """Return the calling participant row (with `auth`: local, bearer or cookie), or raise authentication_required."""
    from daw.commons import accounts
    settings = request.app.state.settings
    if settings.mode == "local":
        return {**archive.participant(settings.local_user), "auth": "local"}
    header = request.headers.get("authorization", "")
    if header:
        scheme, _, token = header.partition(" ")
        participant, _ = accounts.token_participant(archive, token.strip()) if scheme.lower() == "bearer" else (None, None)
        if participant is None:
            raise DawError("authentication_required", "invalid bearer token")
        return {**participant, "auth": "bearer"}
    participant = accounts.read_session(archive, settings.root, request.cookies.get(accounts.COOKIE))
    if participant is None:
        raise DawError("authentication_required", "log in with a token at POST /api/session")
    return {**participant, "auth": "cookie"}


def authenticate_write(request, archive):
    """Caller for an HTTP write: a human or operator, with the CSRF header unless bearer-authenticated."""
    participant = authenticate(request, archive)
    if participant["auth"] != "bearer" and request.headers.get(CSRF_HEADER) != "1":
        raise DawError("permission_denied", f"browser writes must send the {CSRF_HEADER}: 1 header")
    if participant["kind"] not in WRITERS:
        raise DawError("permission_denied", f"{participant['kind']} participants do not write over HTTP; "
                                            "agents use the bio CLI in their checkout")
    return participant
