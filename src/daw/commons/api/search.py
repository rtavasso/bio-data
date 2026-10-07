"""GET /api/search: exact-term (default) or vector search over the library and, optionally, agent workspaces.

Hits on posts hidden by moderation (forum documents) and on their claims are not served (C2): matching a
hidden post's text would disclose it. The response counts them in `withheld_hidden`; `total` is the
catalogs' own count and may include them.
"""
import json

from fastapi import APIRouter

from daw.commons.api.deps import View
from daw.commons.embeddings import search_commons
from daw.commons.moderation import Visibility

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
def search_endpoint(view: View, q: str = "", family: str | None = None, vector: bool = False, scope: str = "library",
                    model: str | None = None, limit: int = 20, offset: int = 0):
    """`scope=workspaces` adds every agent workspace (read-only) to the library; items name their catalog."""
    result = search_commons(view, q, family=family or None, vector=vector, scope=scope, model=model,
                            limit=limit, offset=offset)
    vis = Visibility.of(view)
    items = [_redacted(vis, item) for item in result["items"] if not hidden_hit(view, vis, item)]
    return {**result, "items": items, "withheld_hidden": len(result["items"]) - len(items)}


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
