"""Watcher endpoints (M5.2): list and attach scoped discovery queries, read their immutable runs.

Attaching and disabling are HTTP writes like any other: the caller is an `Actor` (human or operator,
CSRF header unless bearer) and the board is opened in the worker thread by `call`."""
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from daw.commons.api.deps import Config, View
from daw.commons.api.write import Actor, call
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
def create_watcher(body: WatcherInput, who: Actor, config: Config):
    return call(config, add_watcher, who["id"], body.item, body.query, body.provider, body.interval_seconds)


@router.post("/watchers/{watcher}/disable")
def disable(watcher: str, who: Actor, config: Config):
    return call(config, disable_watcher, who["id"], watcher)


@router.get("/watchers/{watcher}/runs")
def watcher_runs(watcher: str, view: View):
    return {"items": runs(view, watcher, receipts=view.library),
            "note": "Runs are retrieval receipts; applicability is the item author's decision"}
