"""`?view=<hash>` for list endpoints (spec v2 V4): the saved view as a dependency, and paging under it.

`Scoped` resolves the query parameter `view` (a saved view's 64-hex hash) to a `savedviews.Scope`, or None.
List endpoints filter their items by recorded fields with `savedviews.page` (see that module for the rules)
and report the view they applied under `view`. Endpoints whose underlying function pages in SQL collect every
page first, so offsets and totals refer to the filtered list.
"""
from typing import Annotated

from fastapi import Depends, Query, Request

from daw.commons import savedviews
from daw.commons.archive import Archive
from daw.commons.api.deps import archive


def scope_param(request: Request, view_archive: Annotated[Archive, Depends(archive)],
                saved: Annotated[str | None, Query(alias="view", description="a saved view's hash")] = None):
    if not saved:
        return None
    return savedviews.Scope.of(view_archive, saved)


Scoped = Annotated[savedviews.Scope | None, Depends(scope_param)]


def collect(fetch, page_size, *, key="items"):
    """Every item of an endpoint that pages in SQL: `fetch(limit, offset)` until a short page."""
    items, offset = [], 0
    while True:
        chunk = fetch(page_size, offset)[key]
        items.extend(chunk)
        if len(chunk) < page_size:
            return items
        offset += page_size


def scoped(result, scope, facts, *, limit=None, offset=0, key="items"):
    """`result` with its items filtered by the view, paged, and `view`/`total` describing the filtered list."""
    kept, window = savedviews.page(result[key], scope, facts, limit=limit, offset=offset)
    out = {**result, key: window, "total": len(kept), "view": scope.describe()}
    if "next_offset" in result or limit is not None:
        out["next_offset"] = offset + limit if limit is not None and offset + limit < len(kept) else None
    if "offset" in result:
        out["offset"] = offset
    return out


question_lookup = savedviews.question_lookup
