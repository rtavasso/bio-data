"""Commons-wide embedding batch and search (M1.8) over the library and participant workspaces.

The model and the per-workspace job live in `daw.embeddings`; this module runs the
job over every catalog of a commons and answers `/api/search`. Embeddings are a
disposable projection beside each catalog's search index. The batch takes each
catalog's own writer lock (non-blocking: a busy workspace is reported and skipped,
never waited on or bypassed); search opens every catalog read-only.
"""
from daw.catalog import Workspace
from daw.embeddings import embed_documents, load_model, vector_search
from daw.search import search
from daw.util import DawError

SCOPES = ("library", "workspaces")


def embed_commons(board, model=None, *, family=None, workspaces=True, allow_download=False):
    """Embed the library and, unless disabled, each agent workspace. Run by the operator (CLI or cron)."""
    model = load_model(model, allow_download=allow_download)
    results = []
    with board.library.writer():
        results.append({"scope": "library", **embed_documents(board.library, model, family=family)})
    if workspaces:
        for agent in board.rows("SELECT id,name FROM agent WHERE trial IS NOT NULL ORDER BY created,id"):
            entry = {"scope": "workspace", "participant": agent["id"], "name": agent["name"]}
            try:
                path = board.trial(board.agent(agent["id"])) / "workspace"
                ws = Workspace(path)
            except DawError as e:
                results.append({**entry, "error": e.reason})
                continue
            try:
                with ws.writer():
                    entry.update(embed_documents(ws, model, family=family))
            except DawError as e:
                entry["error"] = e.reason
            finally:
                ws.close()
            results.append(entry)
    return {"model": model.id, "model_card": model.card(), "sources": results}


def _sources(view, scope):
    if scope not in SCOPES:
        raise DawError("invalid_search_scope", "library or workspaces")
    yield {"scope": "library"}, view.library
    if scope == "workspaces":
        for agent in view.rows("SELECT id,name FROM agent WHERE trial IS NOT NULL ORDER BY created,id"):
            label = {"scope": "workspace", "participant": agent["id"], "name": agent["name"]}
            try:
                yield label, view.workspace(agent["id"])
            except DawError as e:
                yield {**label, "error": e.reason}, None


def search_commons(view, text="", *, family=None, vector=False, scope="library", model=None, limit=20, offset=0):
    """Exact-term (default) or vector search over the library and, with scope=workspaces, every agent workspace.

    Vector scores come from one pinned model and are merged by cosine. Exact-term BM25
    scores depend on each catalog's corpus, so exact results are interleaved by per-source
    rank instead of compared. Every item says which catalog it came from.
    """
    if not 1 <= limit <= 100 or offset < 0:
        raise DawError("invalid_search_bounds")
    if vector and not text.strip():
        raise DawError("empty_vector_query")
    loaded = load_model(model) if vector else None
    sources, ranked = [], []
    for label, ws in _sources(view, scope):
        if ws is None:
            sources.append(label)
            continue
        try:
            result = (vector_search(ws, text, model=loaded, family=family, limit=offset + limit) if vector
                      else search(ws, text, family=family, limit=offset + limit))
        except DawError as e:
            if label["scope"] == "library":
                raise  # invalid arguments; a broken workspace is reported per source instead
            sources.append({**label, "error": e.reason, "detail": e.detail})
            continue
        sources.append({**label, "total": result["total"], **({"coverage": result["coverage"]} if vector else {})})
        items = []
        for rank, item in enumerate(result["items"]):
            item = {k: v for k, v in item.items() if k not in {"fingerprint"}}
            if item.get("format") == "jats-paragraph":
                item["locator"] = item["record_id"]
            items.append({**item, "source": label, "rank": rank})
        ranked.append(items)
    if vector:
        merged = sorted((i for items in ranked for i in items), key=lambda i: (-i["score"], i["id"]))
        method = f"cosine over {loaded.id} vectors, merged across catalogs; the query is embedded, not matched literally"
    else:
        merged = [items[r] for r in range(max((len(x) for x in ranked), default=0)) for items in ranked if r < len(items)]
        method = "SQLite FTS5 per catalog; BM25 is corpus-relative, so catalogs are interleaved by rank"
    total = sum(s.get("total", 0) for s in sources)
    page = merged[offset:offset + limit]
    return {"query": text, "vector": vector, "scope": scope, "family": family, "method": method,
            "model": loaded.id if loaded else None, "total": total, "offset": offset, "items": page,
            "next_offset": offset + len(page) if offset + len(page) < total else None, "sources": sources,
            "content_is_untrusted_data": True,
            "limitations": ["A missing hit is not negative evidence; check each source's coverage and errors",
                            "Exact-term search is primary; vector similarity is a recall aid"]
                           + (["hashing-ngram-v1 matches shared spelling only, not synonyms or meaning"]
                              if vector and loaded.id.startswith("hashing-ngram-v1") else [])}
