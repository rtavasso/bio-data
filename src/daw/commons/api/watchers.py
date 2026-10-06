"""Watcher endpoints (M5.2): list and attach scoped discovery queries, read their immutable runs."""
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from daw.commons.api.deps import Board, Caller, View
from daw.commons.watchers import PROVIDERS, WEEK, add_watcher, disable_watcher, list_watchers, runs

router = APIRouter(prefix="/api", tags=["watchers"])


class WatcherInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str
    query: str | dict[str, Any]
    provider: str
    interval_seconds: int = WEEK


@router.get("/watchers")
def watchers(view: View, item: str | None = None):
    return {"items": list_watchers(view, item), "providers": list(PROVIDERS),
            "cadence": "the operator runs `bio commons watch tick` on a schedule; watchers are weekly by default"}


@router.post("/watchers")
def create_watcher(body: WatcherInput, board: Board, caller: Caller):
    return add_watcher(board, caller, body.item, body.query, body.provider, body.interval_seconds)


@router.post("/watchers/{watcher}/disable")
def disable(watcher: str, board: Board, caller: Caller):
    return disable_watcher(board, caller, watcher)


@router.get("/watchers/{watcher}/runs")
def watcher_runs(watcher: str, view: View):
    return {"items": runs(view, watcher, receipts=view.library),
            "note": "Runs are retrieval receipts; applicability is the item author's decision"}
