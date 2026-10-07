"""Demo extension for discovery: a frontier item for the recorded gap, a weekly watcher, one receipted run
from a recorded (synthetic) Europe PMC response, and pinned-model embeddings for every catalog.

No network is used: the watcher's transport is an httpx.MockTransport that serves a fixture, labelled
synthetic in its own payload, for the Europe PMC search URL only.
"""
import time

import httpx

from daw.commons.demo import SYNTHETIC, _no_reserve
from daw.commons.embeddings import embed_commons
from daw.commons.watchers import add_watcher, list_watchers, open_workspace, tick
from daw.util import DawError

RECORDED_SEARCH = {
    "version": "6.9", "hitCount": 1,
    "request": {"queryString": "demo marker knockdown", "resultType": "core", "cursorMark": "*", "pageSize": 25},
    "resultList": {"result": [{
        "id": "DEMO0001", "source": "SYNTHETIC", "title": "Per-sample counts after demo marker knockdown (synthetic fixture)",
        "authorString": "Synthetic Demo Consortium.", "pubYear": "2026",
        "abstractText": SYNTHETIC}]}}


def recorded_transport(payload=RECORDED_SEARCH):
    def handler(request):
        if request.url.host == "www.ebi.ac.uk" and request.url.path.endswith("/europepmc/webservices/rest/search"):
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not part of the recorded fixture"})
    return httpx.MockTransport(handler)


def ensure_gap_item(board, ctx):
    """The frontier item indexed from the demo's recorded retrieval gap (dana's own workspace event). The
    platform never inserts frontier items: the projection is rebuilt from workspace records and board events."""
    from daw.commons.frontier import item_id, rebuild_frontier
    identity = item_id(ctx["agents"]["dana"], ctx["gap_event"])
    if not board.one("SELECT id FROM frontier_item WHERE id=?", (identity,)):
        rebuild_frontier(board, reason="discovery demo")
    if not board.one("SELECT id FROM frontier_item WHERE id=?", (identity,)):
        raise DawError("unknown_frontier_item", identity)
    return identity


def extend(board, ctx):
    item = ensure_gap_item(board, ctx)
    scratch = open_workspace(board.root)
    scratch.close()
    _no_reserve(scratch.root)
    watcher = next((w for w in list_watchers(board, item) if w["provider"] == "europepmc"), None)
    if watcher is None:
        watcher = add_watcher(board, "operator", item, {"query": "demo marker knockdown"}, "europepmc")
    result = tick(board, now=time.time(), transport=recorded_transport())
    embedded = embed_commons(board)
    ctx["discovery"] = {"frontier_item": item, "watcher": watcher["id"],
                        "watcher_runs": [r["run"] for r in result["ran"] if "run" in r],
                        "notices": [r["notice"]["post"] for r in result["ran"] if r.get("notice")],
                        "embedding_model": embedded["model"]}
