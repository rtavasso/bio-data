"""Claim ledger, contradiction queue, corrections, frontier browser and wishlist (M1.6, M1.7, M5.1, M5.3, M5.4).

Reads use the read-only archive and never write: the frontier projection is
refreshed on the write path (publication, promotion, watcher events) and by the
operator's `bio commons frontier rebuild`, so a GET serves the projection as it
stands and says whether it is behind the workspaces (`projection_current`).
Cluster confirmation is a person's attribution event, written through `Actor` and
`call` like every other HTTP write; nothing here resolves a contradiction or
merges items.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from daw.commons import claims, frontier
from daw.commons.api.deps import Config, View
from daw.commons.api.read import Reader
from daw.commons.api.write import Actor, call
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


def _key(view):
    """Cache key for projection reads: the board sequence (every projection write appends an event)."""
    return view.sequence()


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
def frontier_items(view: View, kind: str | None = None, status: str | None = None,
                   blocked_by: str | None = None, question: str | None = None, author: str | None = None):
    result = frontier.browse(view, kind=kind, status=status, blocked_by=blocked_by, question=question, author=author)
    result["projection_current"] = frontier.is_current(view)
    return result


@router.get("/frontier/clusters")
def frontier_clusters(view: View):
    return _cached(view, "clusters", _key(view), lambda: {"items": frontier.browse(view, status="all")["clusters"]})


class ClusterConfirmation(BaseModel):
    items: list[str] = Field(min_length=2, max_length=50)
    note: str = Field(default="", max_length=2000)


@router.post("/frontier/clusters/confirm")
def confirm(body: ClusterConfirmation, who: Actor, config: Config):
    return call(config, frontier.confirm_cluster, who["id"], body.items, body.note)


@router.get("/frontier/{identity}")
def frontier_item(identity: str, view: View):
    row = view.one("SELECT * FROM frontier_item WHERE id=?", (identity,))
    if not row:
        raise DawError("unknown_frontier_item", identity)
    item = frontier.describe_item(row)
    item["watch"] = frontier.watcher_status(view, [identity])[identity]
    item["question_title"] = frontier.question_titles(view).get(item["question"])
    return frontier.annotate(view, [item])[0]


@router.get("/wishlist")
def dataset_wishlist(view: View):
    # LABBOOK lines are read from workspaces, so the key also covers their work events.
    return _cached(view, "wishlist", frontier.refresh_key(view), lambda: frontier.wishlist(view))
