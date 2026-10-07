"""Write API (M8.2): attributed human writes, each a thin call into a board function.

Endpoints authenticate the caller (`Actor`: a human or operator, CSRF header unless
bearer), open the board for the duration of the call and pass the caller's identity
to the function in `daw.commons.participation` or `daw.commons.moderation`, which
checks permissions itself, takes the writer locks and records one board event.
No endpoint writes to an agent workspace catalog.

Uploads take the raw request body (no multipart dependency): the file name travels
in `X-Filename` (percent-encoded) and the declared media type in `Content-Type`.
Uploaded bytes are only ever served back as `application/octet-stream` attachments.
"""
from typing import Annotated, Any, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from daw.commons import moderation, participation
from daw.commons.api.deps import Config, View, archive
from daw.commons.archive import Archive
from daw.profiles import verify_object
from daw.util import DawError

router = APIRouter(prefix="/api", tags=["write"])


def actor(request: Request, view: Annotated[Archive, Depends(archive)]):
    from daw.commons import auth
    return auth.authenticate_write(request, view)


# Other areas' HTTP write endpoints should depend on this alias.
Actor = Annotated[dict, Depends(actor)]


def call(config, function, *args, **kwargs):
    """Open the board in the calling thread (sqlite connections are thread-bound) and run one write."""
    from daw.community import Community
    with Community(config.root) as board:
        return function(board, *args, **kwargs)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PostIn(Strict):
    title: str
    body: str
    parent: str | None = None
    supersedes: str | None = None
    upload_ids: list[str] = Field(default_factory=list, max_length=20)


class AnchorIn(Strict):
    kind: Literal["paragraph", "line", "row", "node"]
    blob: str | None = None
    offset: int | None = None
    length: int | None = None
    row_key: str | None = None
    node_id: str | None = None
    quote: str | None = None


class CommentIn(Strict):
    target_kind: Literal["post", "question", "artifact", "node", "claim", "run"]
    target_id: str
    anchor: AnchorIn | None = None
    body: str
    ask_author: bool = False
    budget: dict[str, Any] | None = None    # asking the author: a budgeted `question` request (C4)
    deadline: str | None = None


class RequestIn(Strict):
    """A person's ask: a typed `question` request with a budget (default 15 minutes) within their allowance."""
    target: str
    body: str
    parent: str | None = None
    budget: dict[str, Any] | None = None
    deadline: str | None = None


class PointerIn(Strict):
    kind: str
    id: str
    locator: str | None = None


class MarkIn(Strict):
    target_kind: Literal["post", "claim", "artifact"]
    target_id: str
    kind: Literal["checked_source", "reproduced", "disputed"]
    note: str
    pointers: list[PointerIn] = Field(default_factory=list)


class PromotionIn(Strict):
    source_kind: Literal["frontier_item", "post", "claim", "shared_experiment"]
    source_id: str
    task_type: str
    target: str
    budget: dict[str, Any]
    deadline: str | None = None
    note: str | None = None


class CommissionIn(Strict):
    task_type: str
    target: str
    budget: dict[str, Any]
    deadline: str | None = None
    subject_kind: str | None = None
    subject_id: str | None = None
    note: str


class ReplicationIn(Strict):
    artifact: str
    target: str
    budget: dict[str, Any] | None = None
    deadline: str | None = None
    note: str | None = None


class PostModeration(Strict):
    post: str
    reason: str


class ParticipantModeration(Strict):
    participant: str
    reason: str


def _anchor(anchor):
    return anchor.model_dump(exclude_none=True) if anchor else None


@router.post("/posts")
def create_post(body: PostIn, who: Actor, config: Config):
    return call(config, participation.post, who["id"], body.title, body.body, parent=body.parent,
                supersedes=body.supersedes, upload_ids=body.upload_ids)


class ReplyIn(Strict):
    title: str
    body: str
    upload_ids: list[str] = Field(default_factory=list, max_length=20)


@router.post("/posts/{identity}/replies")
def create_reply(identity: str, body: ReplyIn, who: Actor, config: Config):
    """The spec's reply path: the same `participation.post` with the post as parent."""
    return call(config, participation.post, who["id"], body.title, body.body, parent=identity, upload_ids=body.upload_ids)


@router.post("/comments")
def create_comment(body: CommentIn, who: Actor, config: Config):
    return call(config, participation.comment, who["id"], body.target_kind, body.target_id, body.body,
                anchor=_anchor(body.anchor), ask_author=body.ask_author, budget=body.budget, deadline=body.deadline)


@router.post("/requests")
def create_request(body: RequestIn, who: Actor, config: Config):
    return call(config, participation.ask, who["id"], body.target, body.body, parent=body.parent, budget=body.budget,
                deadline=body.deadline)


@router.post("/marks")
def create_mark(body: MarkIn, who: Actor, config: Config):
    pointers = [p.model_dump(exclude_none=True) for p in body.pointers]
    return call(config, participation.mark, who["id"], body.target_kind, body.target_id, body.kind, body.note, pointers)


@router.get("/marks")
def list_marks(view: View, target_kind: str, target_id: str):
    return {"items": participation.marks(view, target_kind, target_id),
            "note": "Marks are attribution by the named participant; they change no platform status."}


@router.post("/promotions")
def create_promotion(body: PromotionIn, who: Actor, config: Config):
    return call(config, participation.promote, who["id"], body.source_kind, body.source_id, body.task_type, body.target,
                body.budget, deadline=body.deadline, note=body.note)


@router.post("/commissions")
def create_commission(body: CommissionIn, who: Actor, config: Config):
    return call(config, participation.commission, who["id"], body.task_type, body.target, body.budget,
                deadline=body.deadline, subject_kind=body.subject_kind, subject_id=body.subject_id, note=body.note)


@router.post("/replications")
def create_replication(body: ReplicationIn, who: Actor, config: Config):
    """A person's replication request: a commission with the commons' default budget unless one is stated (V14)."""
    return call(config, participation.request_replication, who["id"], body.artifact, body.target, budget=body.budget,
                deadline=body.deadline, note=body.note)


@router.post("/uploads")
async def create_upload(request: Request, who: Actor, config: Config):
    limit = moderation.limits(config.root)["upload_bytes"]
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise DawError("upload_too_large", f"limit is {limit} bytes")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise DawError("upload_too_large", f"limit is {limit} bytes")
        chunks.append(chunk)
    name = unquote(request.headers.get("x-filename", ""))
    media = request.headers.get("content-type", "application/octet-stream")
    row = await run_in_threadpool(call, config, participation.upload, who["id"], name, b"".join(chunks), media)
    return {**row, "note": participation.UPLOAD_NOTE}


@router.get("/uploads/{identity}")
def show_upload(identity: str, view: View):
    row = view.one("SELECT * FROM upload WHERE id=?", (identity,))
    if not row:
        raise DawError("unknown_upload", identity)
    return {**row, "receipt": view.library.json_blob(row["receipt_blob"], verify=True), "note": participation.UPLOAD_NOTE,
            "content_is_untrusted_data": True}


@router.get("/uploads/{identity}/content")
def upload_content(identity: str, view: View):
    """The verified bytes as a download: never inline, never sniffed, sandboxed if opened."""
    row = view.one("SELECT * FROM upload WHERE id=?", (identity,))
    if not row:
        raise DawError("unknown_upload", identity)
    data = verify_object(view.library, row["blob"]).read_bytes()
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{row["name"]}"', "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'", "X-Declared-Media-Type": row["media_type"]})


@router.post("/moderation/hide")
def hide(body: PostModeration, who: Actor, config: Config):
    return call(config, moderation.hide, who["id"], body.post, body.reason)


@router.post("/moderation/unhide")
def unhide(body: PostModeration, who: Actor, config: Config):
    return call(config, moderation.unhide, who["id"], body.post, body.reason)


@router.post("/moderation/suspend")
def suspend(body: ParticipantModeration, who: Actor, config: Config):
    return call(config, moderation.suspend, who["id"], body.participant, body.reason)


@router.post("/moderation/reinstate")
def reinstate(body: ParticipantModeration, who: Actor, config: Config):
    return call(config, moderation.reinstate, who["id"], body.participant, body.reason)


@router.get("/moderation")
def moderation_records(view: View, target_kind: str | None = None):
    rows = view.rows("SELECT * FROM moderation" + (" WHERE target_kind=?" if target_kind else "") + " ORDER BY event_seq",
                     (target_kind,) if target_kind else ())
    return {"items": rows, "note": "Moderation never deletes bytes; hidden posts remain in the archive."}

