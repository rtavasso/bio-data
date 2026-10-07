"""Publishing, federation, tours and pilot endpoints (spec v2 V3, V7, V8).

Reads use the read-only archive and never write: tours are re-checked against the archive on every request,
directories and the federation index are read from files and the board. The writes here, a preprint export
and a curated pointer (spec v3 G2), authenticate the caller with the write API's `Actor` (CSRF header unless
bearer; humans and operators only, agents refused) and call `preprint.export_preprint` or `curation.curate`,
which check the `export` or `curate` permission and record one board event.
"""
from typing import Annotated

from fastapi import APIRouter, Query

from daw.commons import curation, directory, export, federation, pilotkit, preprint, tour, views
from daw.commons.api.deps import Config, View
from daw.commons.api.read import Reader
from daw.commons.api.write import Actor, Strict, call
from daw.util import DawError

router = APIRouter(prefix="/api", tags=["publishing"])


class PreprintIn(Strict):
    post: str


class CuratedPointerIn(Strict):
    post: str
    offset: int
    note: str
    artifact: str | None = None
    locator: str | None = None
    unlocatable: bool = False


@router.get("/tours")
def tours(view: View):
    return tour.listing(view)


@router.get("/tours/{name}")
def tour_view(name: str, view: View):
    return tour.get(view, name)


@router.get("/curation/locate")
def curation_locate(view: View, caller: Reader, post: str, offset: int, artifact: str | None = None,
                    full: bool = False):
    """Curators' aid: locators at which a number's value occurs in its post's artifacts (read-only). A hidden
    post is its moderation stub (`full` reveals it only to a holder of `hide`)."""
    return tour.candidates(view, post, offset, artifact, caller=caller, full=full)


@router.post("/curation/pointers")
def curate_pointer(body: CuratedPointerIn, who: Actor, config: Config):
    """A person's curated pointer at a number (artifact + locator), or the number marked unlocatable (G2)."""
    return call(config, curation.curate, who["id"], body.post, body.offset, artifact=body.artifact,
                locator=body.locator, note=body.note, unlocatable=body.unlocatable)


@router.get("/curation/pointers")
def curated_pointers(view: View, caller: Reader, post: str, full: bool = False):
    """Every curation act on a post (oldest first) and its numbers' curation progress. A hidden post is its stub."""
    if not view.one("SELECT id FROM post WHERE id=?", (post,)):
        raise DawError("unknown_post", post)
    vis = views.visibility(view, caller, full)
    if vis.withheld(post):
        return vis.stub(post)
    [progress] = curation.progress(view, [post])
    return {"post": post, "acts": curation.history(view, post), "progress": progress,
            "note": "Curated pointers are people's, attributed to them; never the author's pointers."}


@router.get("/curation/progress")
def curation_progress(view: View, tour_name: Annotated[str, Query(alias="tour")]):
    """Milestone B progress for a tour's finals: numbers resolved by author pointers, curated or unlocatable."""
    return curation.receipt(view, tour.get(view, tour_name, resolved=False))


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
