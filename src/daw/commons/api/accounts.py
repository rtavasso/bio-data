"""Accounts API (M7): the caller's own page, sessions, tokens and operator account management.

GET /api/me answers 401 in accounts mode without a session or bearer token; the web
app then shows /login. Session and token writes follow the same CSRF rule as every
other write (see `daw.commons.auth`). Failed logins are rate limited per client
address and per presented token (`daw.commons.ratelimit`); session cookies are
scoped to the commons' base path, so tenants on one host never share a cookie.
"""
import json
import math
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from daw.commons import accounts, participation
from daw.commons.api.deps import Caller, Config, View, archive
from daw.commons.api.write import Actor, call
from daw.commons.archive import Archive
from daw.commons.auth import CSRF_HEADER, WRITERS
from daw.commons.participants import describe
from daw.commons.permissions import actions, is_visitor, suspended
from daw.commons.ratelimit import token_key
from daw.commons.tasks import TASK_TYPES
from daw.util import DawError

router = APIRouter(prefix="/api", tags=["accounts"])
RECENT = 200


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileIn(Strict):
    display_name: str | None = None
    affiliation: str | None = None
    orcid: str | None = None


class LoginIn(Strict):
    token: str


class VisitorIn(Strict):
    display_name: str
    affiliation: str | None = None


class TokenIn(Strict):
    participant: str | None = None
    label: str = ""


class ParticipantIn(Strict):
    name: str
    kind: str = "human"
    display_name: str | None = None
    affiliation: str | None = None
    orcid: str | None = None


class AllowanceIn(Strict):
    minutes: int | None = None
    tokens: int | None = None
    download_bytes: int | None = None


def summary(view, participant, mode):
    """Identity, permissions, budget and the participant's own attributed writes (read-only archive)."""
    from daw.commons.moderation import Visibility
    pid = participant["id"]
    vis = Visibility.of(view, participant)  # the author's own hidden posts are withheld like anyone's (C2)
    posts = view.rows("SELECT * FROM post WHERE author=? ORDER BY seq DESC LIMIT ?", (pid, RECENT))
    comments, authored = [], []
    for row in posts:
        if vis.withheld(row["id"]):
            authored.append(vis.stub(row["id"]))
            continue
        content = view.library.json_blob(row["body_blob"])
        evidence = content.get("evidence") or {}
        if content.get("kind") == "comment":
            request = view.one("SELECT id,state,target,answer FROM request WHERE post=?", (row["id"],))
            comments.append({"id": row["id"], "created": row["created"], "parent": row["parent"], "body": content["body"],
                             "target": evidence.get("target"),
                             "anchor": vis.anchor(evidence.get("anchor"), evidence.get("target")), "request": request})
        elif content.get("kind") not in {"promotion", "commission"}:
            authored.append({"id": row["id"], "created": row["created"], "title": content["title"],
                             "kind": content.get("kind"), "parent": row["parent"]})
    tasks = view.rows("SELECT r.*,p.created AS posted FROM request r JOIN post p ON p.id=r.post WHERE p.author=? AND "
                      "r.task_type IN (%s) ORDER BY r.created DESC LIMIT ?" % ",".join("?" * len(TASK_TYPES)),
                      (pid, *TASK_TYPES, RECENT))
    for row in tasks:
        row["kind"] = view.library.json_blob(view.one("SELECT body_blob FROM post WHERE id=?", (row["post"],))["body_blob"]
                                             ).get("kind")
    marks = view.rows("SELECT * FROM mark WHERE participant=? ORDER BY created DESC LIMIT ?", (pid, RECENT))
    # Federation imports this participant made (spec v3 B9): one `snapshot_imported` event per import act.
    imports = []
    for row in view.rows("SELECT seq,body,created FROM event WHERE kind='snapshot_imported' AND "
                         "json_extract(body,'$.actor')=? ORDER BY seq DESC LIMIT ?", (pid, RECENT)):
        body = json.loads(row["body"])
        imports.append({**{k: body.get(k) for k in ("snapshot", "already_imported", "scope", "counts", "index")},
                        "seq": row["seq"], "created": row["created"]})
    kind = participant.get("kind", "agent")
    return {**describe(participant), "mode": mode, "auth": participant.get("auth"),
            "permissions": sorted(actions(participant)), "visitor": is_visitor(participant), "writes_over_http": kind in WRITERS,
            "suspended": suspended(view, pid), "budget": participation.budget_summary(view, participant),
            "posts": authored, "comments": comments,
            "promotions": [participation.request_row(r) for r in tasks if r["kind"] == "promotion"],
            "commissions": [participation.request_row(r) for r in tasks if r["kind"] == "commission"],
            "marks": [participation.mark_row(r) for r in marks],
            "uploads": view.rows("SELECT * FROM upload WHERE uploader=? ORDER BY created DESC LIMIT ?", (pid, RECENT)),
            "imports": imports,
            "inbox": view.rows("SELECT * FROM request WHERE target=? AND state!='completed' ORDER BY created", (pid,)),
            "tokens": accounts.tokens(view, pid),
            "csrf_header": CSRF_HEADER}


@router.get("/me")
def me(participant: Caller, view: View, config: Config):
    return summary(view, participant, config.mode)


@router.patch("/me")
def edit_me(body: ProfileIn, who: Actor, config: Config):
    changes = {k: (v or "") for k, v in body.model_dump(exclude_unset=True).items()}
    return describe(call(config, accounts.edit_profile, who["id"], changes))


def _login_view(request: Request, view: Annotated[Archive, Depends(archive)]):
    if request.app.state.settings.mode != "accounts":
        raise DawError("local_mode_has_no_login", "local mode acts as its single local participant")
    if request.headers.get(CSRF_HEADER) != "1":
        raise DawError("permission_denied", f"send the {CSRF_HEADER}: 1 header")
    return view


@router.post("/session")
def login(body: LoginIn, request: Request, view: Annotated[Archive, Depends(_login_view)], config: Config):
    # Failed attempts are counted per client address and per presented token (daw.commons.ratelimit).
    limiter = request.app.state.login_limiter
    token = body.token.strip()
    keys = ("ip:" + (request.client.host if request.client else "unknown"), token_key(token))
    wait = limiter.retry_after(*keys)
    if wait:
        return JSONResponse({"error": "rate_limited", "detail": "too many failed login attempts; try again later"},
                            status_code=429, headers={"Retry-After": str(math.ceil(wait))})
    participant, credential = accounts.token_participant(view, token)
    if participant is None:
        limiter.failed(*keys)
        raise DawError("authentication_required", "unknown or revoked token")
    if participant["kind"] not in WRITERS:
        limiter.failed(*keys)
        raise DawError("permission_denied", f"{participant['kind']} participants do not log in to the web app")
    response = JSONResponse({**describe(participant), "mode": config.mode})
    response.set_cookie(accounts.COOKIE, accounts.sign_session(config.root, credential, participant["id"]),
                        max_age=accounts.SESSION_SECONDS, httponly=True, samesite="strict", path=config.base,
                        secure=request.url.scheme == "https")
    return response


def _visitor_view(request: Request, view: Annotated[Archive, Depends(archive)]):
    if request.headers.get(CSRF_HEADER) != "1":
        raise DawError("permission_denied", f"send the {CSRF_HEADER}: 1 header")
    return view


@router.post("/visitors")
def visitor_sign_in(body: VisitorIn, request: Request, view: Annotated[Archive, Depends(_visitor_view)], config: Config):
    """Spec v3 V15: a visitor's lightweight sign-in on a public commons (`daw.commons.visitors`). Creates a visitor
    participant (comment and mark only), returns a token shown once and sets the session cookie."""
    from daw.commons import visitors
    if not visitors.enabled(config):
        raise DawError("visitor_signin_disabled", "this commons does not offer visitor sign-in ([visitors] signin "
                                                  "in commons.toml, accounts mode, public read policy)")
    limiter = request.app.state.login_limiter
    key = "visitor-ip:" + (request.client.host if request.client else "unknown")
    wait = limiter.retry_after(key)
    if wait:
        return JSONResponse({"error": "rate_limited", "detail": "too many visitor sign-ins; try again later"},
                            status_code=429, headers={"Retry-After": str(math.ceil(wait))})
    person, issued = call(config, visitors.sign_in, body.display_name, affiliation=body.affiliation)
    limiter.failed(key)  # every sign-in from an address counts against its [login] attempt window
    response = JSONResponse({**describe(person), "mode": config.mode, "visitor": True, "token": issued["token"],
                             "note": "Keep this token to sign in again (POST /api/session); only its hash is kept. "
                                     "Visitors read, comment and mark; their acts are attributed to them."})
    response.set_cookie(accounts.COOKIE, accounts.sign_session(config.root, issued["credential"]["id"], person["id"]),
                        max_age=accounts.SESSION_SECONDS, httponly=True, samesite="strict", path=config.base,
                        secure=request.url.scheme == "https")
    return response


@router.delete("/session")
def logout(request: Request, config: Config):
    if request.headers.get(CSRF_HEADER) != "1":
        raise DawError("permission_denied", f"send the {CSRF_HEADER}: 1 header")
    response = JSONResponse({"logged_out": True})
    response.delete_cookie(accounts.COOKIE, path=config.base, httponly=True, samesite="strict")
    return response


@router.get("/tokens")
def list_tokens(participant: Caller, view: View):
    everyone = participant.get("kind") == "operator"
    return {"items": accounts.tokens(view, None if everyone else participant["id"])}


@router.post("/tokens")
def create_token(body: TokenIn, who: Actor, config: Config):
    return call(config, accounts.issue_token, who["id"], body.participant, body.label)


@router.delete("/tokens/{credential}")
def revoke_token(credential: str, who: Actor, config: Config):
    return call(config, accounts.revoke_token, who["id"], credential)


@router.post("/participants")
def create_participant(body: ParticipantIn, who: Actor, config: Config):
    profile = {k: v for k, v in {"display_name": body.display_name, "affiliation": body.affiliation,
                                 "orcid": body.orcid}.items() if v}
    return describe(call(config, accounts.create_participant, who["id"], body.name, body.kind, profile))


@router.put("/participants/{identity}/allowance")
def set_allowance(identity: str, body: AllowanceIn, who: Actor, config: Config):
    return call(config, participation.set_allowance, who["id"], identity, body.model_dump(exclude_none=True))
