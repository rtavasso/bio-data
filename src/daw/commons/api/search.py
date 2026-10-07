"""GET /api/search: exact-term (default) or lexical-vector search over the library and, optionally, agent workspaces.

Hits on posts hidden by moderation (forum documents) and on their claims are not served (C2): matching a
hidden post's text would disclose it. The response counts them in `withheld_hidden`; `total` is the
catalogs' own count and may include them.
"""
import json

from fastapi import APIRouter

from daw.commons.api.deps import View
from daw.commons.api.scoping import Scoped, scoped
from daw.commons.embeddings import search_commons
from daw.commons.moderation import Visibility
from daw.util import DawError

router = APIRouter(prefix="/api", tags=["search"])


def hidden_hit(view, vis, item):
    """True when a search hit is a withheld post or a claim of one."""
    if not vis.records or vis.reveal:
        return False
    family, subject = item.get("family"), item.get("subject")
    if family == "forum":
        return vis.withheld(subject)
    if family == "claim":
        row = view.one("SELECT post FROM claim WHERE id=?", (subject,))
        return bool(row) and vis.withheld(row["post"])
    return False


@router.get("/search")
def search_endpoint(view: View, saved: Scoped, q: str = "", family: str | None = None, vector: bool = False,
                    scope: str = "library", model: str | None = None, limit: int = 20, offset: int = 0,
                    paragraphs: bool = False):
    """`scope=workspaces` adds every agent workspace (read-only) to the library; items name their catalog.
    Article paragraphs are their own search: `paragraphs=true` (or `family=paragraph`); otherwise left out.
    `?view=` (a saved view, V4) keeps hits on posts and claims whose recorded author, question and time match;
    other documents record none of those and are left out under a participant or question constraint."""
    if saved is None:
        result = search_commons(view, q, family=family or None, vector=vector, scope=scope, model=model,
                                limit=limit, offset=offset, paragraphs=paragraphs)
    else:
        if not 1 <= limit <= 100 or offset < 0:
            raise DawError("invalid_search_bounds", f"limit must be 1..100 and offset >= 0 (got limit={limit}, offset={offset})")
        result, hits = None, []
        for start in range(0, SCOPED_HITS, 100):
            result = search_commons(view, q, family=family or None, vector=vector, scope=scope, model=model,
                                    limit=100, offset=start, paragraphs=paragraphs)
            hits.extend(result["items"])
            if len(result["items"]) < 100:
                break
        result = {**result, "items": hits}
    vis = Visibility.of(view)
    items = [_redacted(vis, item) for item in result["items"] if not hidden_hit(view, vis, item)]
    withheld = len(result["items"]) - len(items)
    if saved is not None:
        return {**scoped({**result, "items": items}, saved, _hit_facts(view), limit=limit, offset=offset),
                "withheld_hidden": withheld, "view_considered": SCOPED_HITS}
    return {**result, "items": items, "withheld_hidden": withheld}


SCOPED_HITS = 1000  # under a saved view, the first 1000 hits are filtered and paged in the commons layer


def _hit_facts(view):
    from daw.commons.savedviews import post_questions
    from daw.commons.views import thread_index
    posts = thread_index(view)["posts"]

    def facts(item):
        family, subject = item.get("family"), item.get("subject")
        if family == "forum" and subject in posts:
            row = posts[subject]
            return {row["author"]}, post_questions(row["content"]), row["created"]
        if family == "claim":
            claim = view.one("SELECT author,post,created FROM claim WHERE id=?", (subject,))
            if claim and claim["post"] in posts:
                return {claim["author"]}, post_questions(posts[claim["post"]]["content"]), claim["created"]
        return set(), set(), item.get("created")
    return facts


def _redacted(vis, item):
    """A visible document whose indexed detail quotes a hidden post (a comment's anchor) loses that detail's text."""
    detail = item.get("detail")
    try:
        parsed = json.loads(detail) if isinstance(detail, str) else detail
    except ValueError:
        return item
    if not vis.touches(parsed):
        return item
    scrubbed = vis.scrub(parsed)
    return {**item, "detail": json.dumps(scrubbed) if isinstance(detail, str) else scrubbed, "snippet": None}
