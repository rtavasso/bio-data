"""Number checker endpoints (C5, C11, V2): stored write-up verdicts, the artifact at a locator, number reports.

Read-only: verdicts are recorded by the runtime at delivery (daw.commons.checks.record); these endpoints
read them. `GET /api/artifacts/{id}/locate?locator=row=B_vs_A;col=log2_ratio` returns the table window (or
JSON value, or lines) the artifact page opens at, with the cited cell; bytes are read from the archive,
checked against their sha256 and never executed.
"""
import json

from fastapi import APIRouter

from daw.commons import checks, locators, views
from daw.commons.api.deps import View
from daw.util import DawError

router = APIRouter(prefix="/api", tags=["checker"])


@router.get("/artifacts/{identity}/locate")
def locate(identity: str, view: View, locator: str | None = None):
    return locators.locate(view, identity, locator)


@router.get("/writeup-checks/{post}")
def writeup_check(post: str, view: View):
    """Every recorded verdict on a write-up (oldest first) and the latest verdict body."""
    if not view.one("SELECT id FROM post WHERE id=?", (post,)):
        raise DawError("unknown_post", post)
    history = []
    for row in view.rows("SELECT seq,body,created FROM event WHERE kind=? ORDER BY seq", (checks.EVENT,)):
        body = json.loads(row["body"])
        if body.get("post") == post:
            history.append({"seq": row["seq"], "created": row["created"], **body})
    hidden = post in views.hidden_posts(view)
    if hidden:  # hidden content stays hidden here too: status and counts only
        history = [{k: h[k] for k in ("seq", "created", "post", "request", "status", "rules", "stats")} for h in history]
    latest = None if hidden or not history else checks.verdict_body(view, history[-1])
    return {"post": post, "history": history, "latest": latest, "hidden": hidden, "content_is_untrusted_data": True,
            "note": "A verdict is recorded when a writing or digest task is delivered; refused write-ups are "
                    "withheld on every surface."}


@router.get("/numbers/{post}")
def numbers(post: str, view: View):
    """The number report of one post (scopes, statuses, pointers); a hidden or withheld post reports nothing."""
    detail = views.post_view(view, post)
    return {"post": post, "numbers": detail.get("numbers", []), "summary": detail.get("number_summary"),
            "unpointed": detail.get("unpointed_numbers", []), "post_scoped": detail.get("post_scoped_numbers", []),
            "hidden": bool(detail.get("hidden")), "withheld": bool(detail.get("withheld"))}
