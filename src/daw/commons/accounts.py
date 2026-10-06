"""Accounts (M7): bearer tokens, signed session cookies, profiles and operator account management.

Tokens are random secrets shown once; only their SHA-256 is stored in `credential`.
A person logs in by presenting a token at POST /api/session and receives an
HttpOnly, SameSite=Strict cookie signed with `<commons>/secrets/session.key`
(created 0600). The cookie names its credential, so revoking the token ends every
session made from it. Integrations send `Authorization: Bearer <token>`.

Agents never hold tokens: they act through the bio CLI in their own checkout, and the
HTTP write API refuses agent callers. Every function here checks permissions itself
and records one board event; token values never enter the board or the event log.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid

from daw.commons.participants import add_participant, clean_profile, update_profile
from daw.commons.permissions import require
from daw.util import DawError, canonical, now

TOKEN_PREFIX = "colloquy_"
COOKIE = "colloquy_session"
SESSION_SECONDS = 14 * 24 * 3600
TOKEN_HOLDERS = ("human", "operator", "system")


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def credential_row(row):
    """Public credential fields; the hash is never returned."""
    return {k: row[k] for k in ("id", "participant", "label", "created", "revoked")}


def issue_token(board, actor, participant=None, label=""):
    """Issue a bearer token for yourself, or (operators) for any non-agent participant. The token is shown once."""
    issuer = require(board, board.agent(actor), "token")
    subject = board.agent(participant) if participant else issuer
    if subject["id"] != issuer["id"]:
        require(board, issuer, "participants")
    if subject["kind"] not in TOKEN_HOLDERS:
        raise DawError("agents_use_the_cli", "agents act through bio community in their checkout, not HTTP tokens")
    label = (label or "").strip()
    if len(label) > 100:
        raise DawError("invalid_token_label", "at most 100 characters")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    identity = "credential_" + uuid.uuid4().hex
    with board.writer(), board.db:
        board.db.execute("INSERT INTO credential(id,participant,token_sha256,label,created,revoked) VALUES(?,?,?,?,?,NULL)",
                         (identity, subject["id"], _digest(token), label, now()))
        board.event("token_issued", {"credential": identity, "participant": subject["id"], "issuer": issuer["id"],
                                     "label": label})
    return {"credential": credential_row(board.one("SELECT * FROM credential WHERE id=?", (identity,))), "token": token,
            "note": "Store this token now; only its hash is kept."}


def revoke_token(board, actor, credential):
    """Revoke your own token (or, as an operator, anyone's). Revocation is recorded once and ends its sessions."""
    revoker = require(board, board.agent(actor), "token")
    row = board.one("SELECT * FROM credential WHERE id=?", (credential,))
    if not row:
        raise DawError("unknown_credential", credential)
    if row["participant"] != revoker["id"]:
        require(board, revoker, "participants")
    with board.writer(), board.db:
        if board.one("SELECT revoked FROM credential WHERE id=?", (credential,))["revoked"]:
            raise DawError("credential_already_revoked", credential)
        board.db.execute("UPDATE credential SET revoked=? WHERE id=? AND revoked IS NULL", (now(), credential))
        board.event("token_revoked", {"credential": credential, "participant": row["participant"], "actor": revoker["id"]})
    return credential_row(board.one("SELECT * FROM credential WHERE id=?", (credential,)))


def tokens(db_owner, participant=None):
    sql, params = "SELECT * FROM credential", ()
    if participant:
        sql, params = sql + " WHERE participant=?", (participant,)
    return [credential_row(row) for row in db_owner.rows(sql + " ORDER BY created,id", params)]


def token_participant(db_owner, token):
    """(participant row, credential id) for a live token, else (None, None). Works on Community and Archive."""
    if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX) or len(token) > 200:
        return None, None
    row = db_owner.one("SELECT * FROM credential WHERE token_sha256=? AND revoked IS NULL", (_digest(token),))
    if not row:
        return None, None
    return _participant(db_owner, row["participant"]), row["id"]


def _participant(db_owner, identity):
    row = db_owner.one("SELECT * FROM agent WHERE id=?", (identity,))
    if row:
        row["config"] = json.loads(row["config"])
    return row


def session_key(root):
    """The commons' cookie-signing key, created once with mode 0600 in <commons>/secrets/."""
    folder = root / "secrets"
    folder.mkdir(mode=0o700, exist_ok=True)
    path = folder / "session.key"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "wb") as stream:
            stream.write(secrets.token_bytes(32))
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise DawError("unsafe_session_key", "secrets/session.key must be a regular file readable only by its owner")
    key = path.read_bytes()
    if len(key) < 32:
        raise DawError("unsafe_session_key", "secrets/session.key is too short")
    return key


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_session(root, credential, participant, *, issued=None):
    payload = _b64(canonical({"credential": credential, "participant": participant, "issued": int(issued or time.time())}))
    signature = hmac.new(session_key(root), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def read_session(db_owner, root, value):
    """Participant for a valid, unexpired cookie whose credential is still live; otherwise None."""
    if not value or value.count(".") != 1 or len(value) > 1000:
        return None
    payload, signature = value.split(".")
    expected = hmac.new(session_key(root), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:
        return None
    if not isinstance(body, dict) or not isinstance(body.get("issued"), int) or time.time() - body["issued"] > SESSION_SECONDS:
        return None
    live = db_owner.one("SELECT participant FROM credential WHERE id=? AND revoked IS NULL", (body.get("credential"),))
    if not live or live["participant"] != body.get("participant"):
        return None
    return _participant(db_owner, live["participant"])


def edit_profile(board, actor, changes):
    """Merge profile changes (an empty string clears a field) after the caller's permission check."""
    person = require(board, board.agent(actor), "profile")
    merged = {**person["config"].get("profile", {}), **(changes or {})}
    return update_profile(board, person["id"], clean_profile({k: v for k, v in merged.items() if v}))


def create_participant(board, actor, name, kind="human", profile=None):
    """Operators create human, operator or system participants; agents come from community add-agent."""
    require(board, board.agent(actor), "participants")
    return add_participant(board, name, kind, profile=profile)
