"""Observatory read endpoints for the evidence map, question pages and agent timelines (M4.2–M4.4, M8.1).

All reads go through the read-only Archive. Byte endpoints never serve HTML: text is
text/plain, images are served only when their name and leading bytes agree, SVG is
an attachment, and every response carries nosniff plus a sandboxing CSP.
"""
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from daw.commons import evidence_map, questions, timeline
from daw.commons.api.deps import View

router = APIRouter(prefix="/api", tags=["observatory"])

SAFE_HEADERS = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'",
                "Cross-Origin-Resource-Policy": "same-origin"}


@router.get("/map")
def evidence_graph(view: View, question: str | None = None, participant: str | None = None, since: str | None = None,
                   until: str | None = None, family: str | None = None,
                   limit: int = Query(evidence_map.DEFAULT_LIMIT, ge=1, le=evidence_map.MAX_LIMIT)):
    return evidence_map.evidence_map(view, question=question, participant=participant, since=since, until=until,
                                     family=family, limit=limit)


@router.get("/map/node/{identity}")
def map_node(identity: str, view: View):
    return evidence_map.node_record(view, identity)


@router.get("/questions")
def question_index(view: View, agent: str | None = None, status: str | None = None):
    return questions.question_list(view, agent=agent, status=status)


@router.get("/questions/{qid}")
def question_by_id(qid: str, view: View, snapshot: str | None = None):
    """The spec's GET /api/questions/{id}: a bare question id opens the earliest participant holding it (the
    original author precedes its forks, whose workspaces carry inherited copies), as comments on questions do."""
    from daw.commons.participation import question_owner
    owner, question, _ = question_owner(view, qid)
    return questions.question_page(view, owner, question, snapshot=snapshot)


@router.get("/questions/{agent}/{qid}")
def question(agent: str, qid: str, view: View, snapshot: str | None = None):
    return questions.question_page(view, agent, qid, snapshot=snapshot)


@router.get("/blobs/{owner}/{sha}")
def blob(owner: str, sha: str, view: View, name: str | None = None):
    path, media, filename, attachment = questions.blob_file(view, owner, sha, name)
    headers = {**SAFE_HEADERS, "Cache-Control": "private, max-age=31536000, immutable"}
    return FileResponse(path, media_type=media, filename=filename, headers=headers,
                        content_disposition_type="attachment" if attachment else "inline")


@router.get("/runs")
def runs(view: View, agent: str | None = None, state: str | None = None,
         limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    return timeline.run_list(view, agent=agent, state=state, limit=limit, offset=offset)


@router.get("/runs/{run}")
def run(run: str, view: View):
    return timeline.run_timeline(view, run)


@router.get("/runs/{run}/raw")
def run_raw(run: str, view: View):
    return FileResponse(timeline.raw_stream(view, run), media_type="text/plain; charset=utf-8",
                        filename=f"{run}-events.jsonl", content_disposition_type="inline", headers=SAFE_HEADERS)


@router.get("/runs/{run}/messages")
def run_messages(run: str, view: View, offset: int = Query(0, ge=0),
                 limit: int = Query(50, ge=1, le=timeline.MAX_MESSAGES)):
    return timeline.run_messages(view, run, offset=offset, limit=limit)
