"""Human workbench API (spec v2 V4): saved views, the personal inbox, reading mode, anchored replies, review requests.

Reads use the read-only archive; writes depend on `Actor` and open the board with `write.call`, so each is one
attributed board function under the writer lock:

    POST /api/views                      {questions, participants, since, until} -> {view: <hash>, spec}
    GET  /api/views/{hash}
    GET  /api/me/inbox                   ?after=<seq>&limit=&unread=&view=
    GET  /api/me/inbox/stream            SSE: one `inbox_item` per new item (id: its board seq), per caller
    POST /api/me/inbox/read              {items: [...]} or {all: true}
    GET  /api/threads/{post}/reading     posts, corrections and claims interleaved, with numbers
    POST /api/comments/{post}/replies    {body}: a reply in the comment thread at that anchor
    POST /api/reviews                    {claim, target, budget, comment?|anchor?, deadline?, note?}
"""
import asyncio
import time
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from daw.commons import inbox, participation, reading, savedviews
from daw.commons.api.deps import Caller, Config, View
from daw.commons.api.events import cursor_from, frame
from daw.commons.api.read import Reader
from daw.commons.api.scoping import Scoped
from daw.commons.api.write import Actor, AnchorIn, call

router = APIRouter(prefix="/api", tags=["workbench"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ViewIn(Strict):
    questions: list[str] = Field(default_factory=list, max_length=savedviews.MAX_MEMBERS)
    participants: list[str] = Field(default_factory=list, max_length=savedviews.MAX_MEMBERS)
    since: str | None = None
    until: str | None = None


class ReadIn(Strict):
    items: list[str] = Field(default_factory=list, max_length=inbox.MAX_MARK)
    all: bool = False


class ReplyIn(Strict):
    body: str


class ReviewIn(Strict):
    claim: str
    target: str
    budget: dict[str, Any]
    comment: str | None = None
    anchor: AnchorIn | None = None
    deadline: str | None = None
    note: str | None = None


# ---------------------------------------------------------------------------- saved views

@router.post("/views")
def save_view(body: ViewIn, who: Actor, config: Config):
    return call(config, savedviews.save, who["id"], body.model_dump())


@router.get("/views/{identity}")
def show_view(identity: str, view: View):
    found = savedviews.load(view, identity)
    names = {r["id"]: r["name"] for r in view.rows("SELECT id,name FROM agent")}
    return {**found, "participant_names": {p: names.get(p) for p in found["spec"]["participants"]},
            "rule": "recorded fields only; a record without the field a constraint needs is excluded"}


# ---------------------------------------------------------------------------- inbox

@router.get("/me/inbox")
def my_inbox(participant: Caller, view: View, scope: Scoped, after: Annotated[int, Query(ge=0)] = 0,
             limit: Annotated[int, Query(ge=1, le=500)] = 200, unread: bool = False):
    return inbox.inbox(view, participant, after=after, limit=limit, unread_only=unread, scope=scope)


@router.post("/me/inbox/read")
def mark_inbox_read(body: ReadIn, who: Actor, config: Config):
    return call(config, inbox.mark_read, who["id"], body.items or None, everything=body.all)


def _sequence(root):
    from daw.commons.archive import connect_ro
    db = connect_ro(root / "board.sqlite")
    try:
        return db.execute("SELECT coalesce(max(seq),0) FROM event").fetchone()[0]
    finally:
        db.close()


def _new_items(root, participant, cursor):
    from daw.commons.archive import Archive
    with Archive(root) as view:
        sequence = view.sequence()
        found = inbox.inbox(view, participant, after=cursor, limit=500)
    return sequence, sorted(found["items"], key=lambda i: (i.get("seq") or 0, i["id"]))


async def inbox_stream(root, participant, after, *, once=False, request=None, poll=1.0, keepalive=15.0):
    """Per-caller SSE: each new inbox item once, `id:` its board sequence, so a reconnect resumes after it."""
    cursor, seen_sequence = after, None
    yield "retry: 3000\n\n"
    last = time.monotonic()
    while True:
        sequence = await asyncio.to_thread(_sequence, root)
        if sequence != seen_sequence:
            seen_sequence, items = await asyncio.to_thread(_new_items, root, participant, cursor)
            for item in items:
                cursor = max(cursor, item.get("seq") or 0)
                yield frame("inbox_item", item, seq=item.get("seq"), named=False)
            if items:
                last = time.monotonic()
        if once:
            return
        if request is not None and await request.is_disconnected():
            return
        if time.monotonic() - last >= keepalive:
            last = time.monotonic()
            yield ": keepalive\n\n"
        await asyncio.sleep(poll)


@router.get("/me/inbox/stream")
async def my_inbox_stream(request: Request, participant: Caller, config: Config,
                          after: Annotated[int, Query(ge=0)] = 0, once: bool = False,
                          last_event_id: Annotated[str | None, Header()] = None):
    cursor = cursor_from(after, last_event_id)
    who = {k: participant[k] for k in ("id", "name", "kind")}
    return StreamingResponse(inbox_stream(config.root, who, cursor, once=once, request=request),
                             media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------- reading mode, anchors, reviews

@router.get("/threads/{identity}/reading")
def thread_reading(identity: str, view: View, caller: Reader, full: bool = False):
    return reading.thread_reading(view, identity, caller=caller, full=full)


@router.post("/comments/{identity}/replies")
def reply_at_anchor(identity: str, body: ReplyIn, who: Actor, config: Config):
    return call(config, participation.reply_at_anchor, who["id"], identity, body.body)


@router.post("/reviews")
def request_review(body: ReviewIn, who: Actor, config: Config):
    anchor = body.anchor.model_dump(exclude_none=True) if body.anchor else None
    return call(config, participation.request_review, who["id"], body.claim, body.target, body.budget,
                comment_post=body.comment, anchor=anchor, deadline=body.deadline, note=body.note)
