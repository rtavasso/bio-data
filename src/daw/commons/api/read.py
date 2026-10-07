"""Read API (M8.1) for the observatory board: posts, threads, artifacts, participants, requests, running.

Every endpoint reads the archive with mode=ro connections through `daw.commons.views`. Board content
is returned as attributed, untrusted data. Hidden posts resolve through `daw.commons.moderation.Visibility`:
`full=true` reveals them only to a caller holding `hide`. Artifact bytes are served as text/plain or as an
attachment, never as HTML, with a sandboxing content security policy.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse

from daw.commons import views
from daw.commons.api.deps import View
from daw.commons.api.scoping import Scoped, question_lookup, scoped
from daw.util import DawError

router = APIRouter(prefix="/api", tags=["read"])


def optional_caller(request: Request, view: View):
    """The calling participant when one is authenticated; reads are open to everyone (M7.2)."""
    from daw.commons import auth
    try:
        return auth.authenticate(request, view)
    except DawError as error:
        if error.reason == "authentication_required":
            return None
        raise


Reader = Annotated[dict | None, Depends(optional_caller)]


@router.get("/posts")
def posts(view: View, caller: Reader, scope: Scoped, family: str = "forum", q: str = "", author: str | None = None,
          kind: str | None = None, channel: str | None = None, question: str | None = None, sort: str = "recent",
          limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0, full: bool = False):
    return views.list_posts(view, family=family, q=q, author=author, kind=kind, channel=channel, question=question,
                            sort=sort, limit=limit, offset=offset, full=full, caller=caller, scope=scope)


@router.get("/posts/{identity}")
def post(identity: str, view: View, caller: Reader, full: bool = False):
    return views.post_view(view, identity, caller=caller, full=full)


@router.get("/threads/{identity}")
def thread(identity: str, view: View, caller: Reader, full: bool = False):
    return views.thread_view(view, identity, caller=caller, full=full)


@router.get("/artifacts/{identity}")
def artifact(identity: str, view: View, caller: Reader, depth: Annotated[int, Query(ge=0, le=6)] = 3,
             full: bool = False):
    return views.artifact_view(view, identity, depth=depth, caller=caller, full=full)


@router.get("/artifacts/{identity}/bytes")
def artifact_bytes(identity: str, view: View, download: bool = False):
    found = views.artifact_bytes(view, identity)
    headers = {"Content-Security-Policy": "sandbox; default-src 'none'", "X-Content-Type-Options": "nosniff",
               "X-Content-SHA256": found["sha256"], "Cache-Control": "private, max-age=31536000, immutable"}
    if found["text"] and not download:
        return FileResponse(found["path"], media_type="text/plain; charset=utf-8", headers=headers,
                            content_disposition_type="inline", filename=found["name"])
    return FileResponse(found["path"], media_type="application/octet-stream", headers=headers,
                        content_disposition_type="attachment", filename=found["name"])


@router.get("/participants/{identity}/activity")
def activity(identity: str, view: View, caller: Reader, full: bool = False):
    return views.participant_activity(view, identity, caller=caller, full=full)


@router.get("/requests")
def requests(view: View, caller: Reader, scope: Scoped, target: str | None = None, state: str | None = None,
             task_type: str | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 200, full: bool = False):
    if scope is None:
        return views.list_requests(view, target=target, state=state, task_type=task_type, limit=limit, caller=caller,
                                   full=full)
    everything = views.list_requests(view, target=target, state=state, task_type=task_type, limit=1_000_000,
                                     caller=caller, full=full)
    questions = question_lookup(view, caller, full)
    return scoped(everything, scope, lambda r: ({r.get("asker"), r["target"]}, questions(r["post"]), r["created"]),
                  limit=limit)


@router.get("/running")
def running(view: View, caller: Reader, scope: Scoped, full: bool = False):
    result = views.running(view, caller=caller, full=full)
    if scope is None:
        return result
    questions = question_lookup(view, caller, full)
    return scoped(result, scope, lambda r: ({r["agent"]}, questions(r["post"]), r["started"]))
