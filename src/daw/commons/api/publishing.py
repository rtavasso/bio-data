"""Publishing, federation, tours and pilot endpoints (spec v2 V3, V7, V8).

Reads use the read-only archive and never write: tours are re-checked against the archive on every request,
directories and the federation index are read from files and the board. The one write here, a preprint
export, authenticates the caller with the write API's `Actor` (CSRF header unless bearer) and calls
`preprint.export_preprint`, which checks the `export` permission and records one board event.
"""
from typing import Annotated

from fastapi import APIRouter, Query

from daw.commons import directory, export, federation, pilotkit, preprint, tour
from daw.commons.api.deps import Config, View
from daw.commons.api.write import Actor, Strict, call

router = APIRouter(prefix="/api", tags=["publishing"])


class PreprintIn(Strict):
    post: str


@router.get("/tours")
def tours(view: View):
    return tour.listing(view)


@router.get("/tours/{name}")
def tour_view(name: str, view: View):
    return tour.get(view, name)


@router.get("/curation/locate")
def curation_locate(view: View, post: str, offset: int, artifact: str | None = None):
    """Curators' aid: locators at which a number's value occurs in its post's artifacts (read-only)."""
    return tour.candidates(view, post, offset, artifact)


@router.get("/directory")
def directory_view(view: View):
    return directory.known(view)


@router.get("/directory/{snapshot}")
def directory_snapshot(snapshot: str, view: View):
    """An imported snapshot: its manifest summary, indexed claims and artifacts (with byte routes) and the
    posts of this board that cite it. Foreign, untrusted data."""
    info = export.snapshot_info(view.root, snapshot, verify=False)
    cited = next((s for s in federation.citations(view)["snapshots"] if s["snapshot"] == snapshot), None)
    return {**{k: v for k, v in info.items() if k != "files"}, "file_count": len(info["files"]),
            "records": federation.records(view, snapshot), "citations": cited,
            "pointer_forms": [f"snapshot:{snapshot}/claim_…", f"snapshot:{snapshot}/artifact_…#row=…;col=…"]}


@router.get("/federation-index")
def federation_index(view: View):
    return {"index": federation.indexed(view), "sequence": view.sequence()}


@router.get("/snapshot-citations")
def snapshot_citations(view: View):
    return federation.citations(view)


@router.get("/preprints")
def preprints(view: View):
    import json
    rows = view.rows("SELECT seq,body,created FROM event WHERE kind='preprint_exported' ORDER BY seq DESC")
    return {"preprints": [{**json.loads(r["body"]), "seq": r["seq"], "created": r["created"]} for r in rows]}


@router.post("/preprints")
def create_preprint(body: PreprintIn, who: Actor, config: Config):
    return call(config, preprint.export_preprint, who["id"], body.post)


@router.get("/pilot/report")
def pilot_report(view: View, participant: Annotated[list[str] | None, Query()] = None):
    return pilotkit.report(view, participant)
