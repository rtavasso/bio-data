"""Claim ledger, contradiction queue, corrections, frontier browser and wishlist (M1.6, M1.7, M5.1, M5.3, M5.4).

Reads use the read-only archive. The frontier projection is refreshed from the
participant workspaces before a read when the board sequence or any workspace's
work-event count changed; that refresh is the only write a GET performs and it
goes through `rebuild_frontier` under the board writer lock. Cluster confirmation
is a person's attribution event; nothing here resolves a contradiction or merges items.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from daw.commons import claims, frontier
from daw.commons.api.deps import Board, Caller, Config, View
from daw.commons.api.read import Reader
from daw.util import DawError

router = APIRouter(prefix="/api", tags=["ledger"])
_CACHE: dict = {}


def _cached(view, name, key, compute):
    slot = (str(view.root), name)
    hit = _CACHE.get(slot)
    if hit and hit[0] == key:
        return hit[1]
    value = compute()
    _CACHE[slot] = (key, value)
    return value


def _fresh(view, config):
    frontier.ensure_current(config.root, view)
    return frontier.refresh_key(view)


@router.get("/claims")
def claim_search(view: View, caller: Reader, q: str = "", status: str | None = None, scope: str | None = None,
                 author: str | None = None, post: str | None = None, limit: int = 50, offset: int = 0,
                 full: bool = False):
    return claims.list_claims(view, q, status=status, scope=scope, author=author, post=post, limit=limit, offset=offset,
                              caller=caller, full=full)


@router.get("/claims/contradictions")
def contradiction_queue(view: View):
    return _cached(view, "contradictions", view.sequence(), lambda: claims.contradictions(view))


@router.get("/claims/{identity}")
def claim(identity: str, view: View, caller: Reader, full: bool = False):
    from daw.commons.moderation import Visibility
    row = view.one("SELECT * FROM claim WHERE id=?", (identity,))
    if not row:
        raise DawError("unknown_claim", identity)
    return claims.describe_claim(view, row, vis=Visibility.of(view, caller, full))


@router.get("/corrections/{post}")
def correction(post: str, view: View, caller: Reader, full: bool = False):
    """Flow B: replacements, withdrawn claims and the readers affected by a superseded post."""
    return claims.corrections(view, post, caller=caller, full=full)


@router.get("/frontier")
def frontier_items(view: View, config: Config, kind: str | None = None, status: str | None = None,
                   blocked_by: str | None = None, question: str | None = None, author: str | None = None):
    _fresh(view, config)
    return frontier.browse(view, kind=kind, status=status, blocked_by=blocked_by, question=question, author=author)


@router.get("/frontier/clusters")
def frontier_clusters(view: View, config: Config):
    key = _fresh(view, config)
    return _cached(view, "clusters", key, lambda: {"items": frontier.browse(view, status="all")["clusters"]})


class ClusterConfirmation(BaseModel):
    items: list[str] = Field(min_length=2, max_length=50)
    note: str = Field(default="", max_length=2000)


@router.post("/frontier/clusters/confirm")
def confirm(body: ClusterConfirmation, board: Board, participant: Caller):
    return frontier.confirm_cluster(board, participant["id"], body.items, body.note)


@router.get("/frontier/{identity}")
def frontier_item(identity: str, view: View, config: Config):
    _fresh(view, config)
    row = view.one("SELECT * FROM frontier_item WHERE id=?", (identity,))
    if not row:
        raise DawError("unknown_frontier_item", identity)
    item = frontier.describe_item(row)
    item["watch"] = frontier.watcher_status(view, [identity])[identity]
    item["question_title"] = frontier.question_titles(view).get(item["question"])
    return frontier.annotate(view, [item])[0]


@router.get("/wishlist")
def dataset_wishlist(view: View, config: Config):
    key = _fresh(view, config)
    return _cached(view, "wishlist", key, lambda: frontier.wishlist(view))
