"""GET /api/search: exact-term (default) or lexical-vector search over the library and, optionally, agent workspaces."""
from fastapi import APIRouter

from daw.commons.api.deps import View
from daw.commons.embeddings import search_commons

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search_endpoint(view: View, q: str = "", family: str | None = None, vector: bool = False, scope: str = "library",
                    model: str | None = None, limit: int = 20, offset: int = 0, paragraphs: bool = False):
    """`scope=workspaces` adds every agent workspace (read-only) to the library; items name their catalog.
    Article paragraphs are their own search: `paragraphs=true` (or `family=paragraph`); otherwise left out."""
    return search_commons(view, q, family=family or None, vector=vector, scope=scope, model=model,
                          limit=limit, offset=offset, paragraphs=paragraphs)
