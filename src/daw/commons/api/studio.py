"""Studio, export and federation endpoints (M6, M8.4).

Reads use the read-only archive. A write-up the renderer refuses is served as HTTP 422 with every
unpointed number and unresolved pointer; a write-up citing withdrawn claims is served only with
`regeneration_required`. Writes (reviews, digests, exports, replication checks) authenticate the
caller with the write API's `Actor` and call Studio functions, which check permissions themselves.
Federated snapshot files are served read-only as text or attachments, labelled foreign.
"""
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import Field

from daw.commons import export, studio, writeup
from daw.commons.api.deps import Config, View
from daw.commons.api.write import Actor, PointerIn, Strict, call

router = APIRouter(prefix="/api", tags=["studio"])
SAFE_HEADERS = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'",
                "Cross-Origin-Resource-Policy": "same-origin"}


class VerdictIn(Strict):
    criterion: str
    verdict: Literal["supported", "partially_supported", "not_supported", "not_assessable", "reproduced"]
    note: str = ""
    pointers: list[PointerIn] = Field(default_factory=list, max_length=50)


class ReviewIn(Strict):
    target_kind: Literal["post", "claim", "artifact"]
    target_id: str
    verdicts: list[VerdictIn] = Field(min_length=1, max_length=50)
    summary: str = ""


class DigestScope(Strict):
    query: str | None = None
    questions: list[str] = Field(default_factory=list, max_length=100)
    posts: list[str] = Field(default_factory=list, max_length=100)


class DigestIn(Strict):
    target: str
    scope: DigestScope = Field(default_factory=DigestScope)
    budget: dict[str, Any]
    since: str | None = None
    until: str | None = None
    deadline: str | None = None
    note: str | None = None


class ScheduleIn(Strict):
    target: str
    scope: DigestScope = Field(default_factory=DigestScope)
    cadence: Literal["daily", "weekly"] | int
    budget: dict[str, Any]
    start: str | None = None


class ExportIn(Strict):
    scope: Literal["board", "thread", "question"]
    id: str | None = None


def _scope(scope):
    return scope.model_dump(exclude_none=True, exclude_defaults=True)


@router.get("/studio")
def studio_overview(view: View):
    return studio.overview(view)


@router.get("/studio/writeups/{post}")
def render(post: str, view: View):
    result = writeup.render_writeup(view, post)
    if result["status"] == "refused":
        return JSONResponse({"error": "writeup_refused", "detail": f"{len(result['problems'])} problem(s)", **result},
                            status_code=422)
    return result


@router.post("/studio/reviews")
def submit_review(body: ReviewIn, who: Actor, config: Config):
    verdicts = [{**v.model_dump(exclude={"pointers"}), "pointers": [p.model_dump(exclude_none=True) for p in v.pointers]}
                for v in body.verdicts]
    return call(config, studio.submit_review, who["id"], body.target_kind, body.target_id, verdicts, body.summary)


@router.get("/studio/digests")
def digests(view: View):
    return {"schedules": [studio.schedule_row(r) for r in view.rows("SELECT * FROM digest_schedule ORDER BY created DESC")]}


@router.get("/studio/digest-skeleton")
def skeleton(view: View, questions: Annotated[list[str] | None, Query()] = None,
             posts: Annotated[list[str] | None, Query()] = None, query: str | None = None, since: str | None = None,
             until: str | None = None):
    scope = {k: v for k, v in {"query": query, "questions": questions, "posts": posts}.items() if v}
    return studio.digest_skeleton(view, scope, since, until)


@router.post("/studio/digests/commission")
def commission_digest(body: DigestIn, who: Actor, config: Config):
    return call(config, studio.commission_digest, who["id"], body.target, _scope(body.scope), body.budget,
                since=body.since, until=body.until, deadline=body.deadline, note=body.note)


@router.post("/studio/digests")
def schedule_digest(body: ScheduleIn, who: Actor, config: Config):
    return call(config, studio.schedule_digest, who["id"], body.target, _scope(body.scope), body.cadence, body.budget,
                start=body.start)


@router.delete("/studio/digests/{schedule}")
def cancel_digest(schedule: str, who: Actor, config: Config):
    return call(config, studio.cancel_digest, who["id"], schedule)


@router.post("/studio/replications/{request}/check")
def check_replication(request: str, who: Actor, config: Config):
    return call(config, studio.replication_check, request, actor=who["id"])


@router.post("/exports")
def create_export(body: ExportIn, who: Actor, config: Config):
    return call(config, export.export_snapshot, who["id"], body.scope, body.id)


@router.get("/exports")
def exports(view: View):
    return {"exports": studio.overview_exports(view)}


@router.get("/federation")
def federation(view: View):
    return {"snapshots": export.list_snapshots(view.root), "foreign": True, "content_is_untrusted_data": True}


@router.get("/federation/{snapshot}")
def federated_snapshot(snapshot: str, view: View, verify: bool = False):
    return export.snapshot_info(view.root, snapshot, verify=verify)


@router.get("/federation/{snapshot}/files/{path:path}")
def federated_file(snapshot: str, path: str, view: View):
    target, media, name, attachment = export.snapshot_file(view.root, snapshot, path)
    return FileResponse(target, media_type=media, filename=name, content_disposition_type="attachment" if attachment
                        else "inline", headers={**SAFE_HEADERS, "X-Colloquy-Foreign-Snapshot": snapshot,
                                                "Cache-Control": "private, max-age=31536000, immutable"})
