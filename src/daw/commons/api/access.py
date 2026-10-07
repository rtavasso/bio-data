"""Read policy, membership and the operator audit log (spec v2 V9).

    GET  /api/access                       the commons' read policy and the caller's standing (open to all)
    GET  /api/members                      operators: membership records of a private commons
    POST /api/members                      operators: {participant, reason} grants membership
    POST /api/members/{participant}/revoke operators: {reason} revokes it
    GET  /api/audit                        operators: board events by kind, participant and time, paged

The policy itself is enforced for every request by `daw.commons.access.ReadPolicy` (the app middleware).
"""
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from daw.commons import access, audit
from daw.commons.api.deps import Caller, Config, View
from daw.commons.api.write import Actor, call
from daw.commons.permissions import require

router = APIRouter(prefix="/api", tags=["access"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GrantIn(Strict):
    participant: str
    reason: str = Field(default="", max_length=2000)


class RevokeIn(Strict):
    reason: str = Field(default="", max_length=2000)


@router.get("/access")
def access_standing(request: Request, view: View, config: Config):
    return access.standing(view, config, access.caller(request.scope, view))


@router.get("/members")
def list_members(participant: Caller, view: View, config: Config):
    require(view, participant, "participants")
    return {"read_policy": config.access, "items": access.members(view),
            "note": "Operators always read; under a private policy only granted members do."}


@router.post("/members")
def grant_member(body: GrantIn, who: Actor, config: Config):
    return call(config, access.grant, who["id"], body.participant, body.reason)


@router.post("/members/{identity}/revoke")
def revoke_member(identity: str, body: RevokeIn, who: Actor, config: Config):
    return call(config, access.revoke, who["id"], identity, body.reason)


@router.get("/audit")
def audit_events(participant: Caller, view: View, kind: str | None = None,
                 who: Annotated[str | None, Query(alias="participant")] = None,
                 since: str | None = None, until: str | None = None,
                 before: Annotated[int | None, Query(ge=1)] = None,
                 limit: Annotated[int, Query(ge=1, le=audit.MAX_LIMIT)] = 100, full: bool = False):
    kinds = [k for k in (kind or "").split(",") if k.strip()]
    return audit.audit_log(view, participant, kinds=kinds, participant=who, since=since, until=until, before=before,
                           limit=limit, full=full)
