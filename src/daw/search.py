"""Local full-text, exact-content and optional externally computed vector search."""
import json
import math
import re

from daw.substrate_models import Embedding
from daw.util import DawError, canonical, digest, read_json


def index_document(ws, *, key, family, subject, record_id, title, summary, body_blob,
                   detail="", provider="local", format="", level=0):
    # This is a disposable projection. Source/profile/work snapshots are immutable.
    text = detail if isinstance(detail, str) else canonical(detail).decode()
    text = text[:256000]
    fingerprint = digest([title, summary, text, body_blob])
    with ws.db:
        ws.db.execute("DELETE FROM search_fts WHERE id=?", (key,))
        ws.db.execute("INSERT INTO search_document VALUES(?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET record_id=excluded.record_id,title=excluded.title,summary=excluded.summary,"
            "provider=excluded.provider,format=excluded.format,level=excluded.level,body_blob=excluded.body_blob,fingerprint=excluded.fingerprint",
            (key, family, subject, record_id, title, summary, provider, format, level, body_blob, fingerprint))
        ws.db.execute("INSERT INTO search_fts(id,title,summary,detail) VALUES(?,?,?,?)", (key, title, summary, text))
    return key


def add_embedding(ws, value: Embedding):
    row = ws.one("SELECT fingerprint FROM search_document WHERE id=?", (value.document_id,))
    if not row or row["fingerprint"] != value.fingerprint:
        raise DawError("embedding_document_changed", "embed the current compact search document")
    norm = math.sqrt(sum(x*x for x in value.vector))
    if not math.isfinite(norm) or norm == 0:
        raise DawError("invalid_embedding", "finite, nonzero vectors required")
    previous = ws.one("SELECT dimensions FROM search_embedding WHERE model=? LIMIT 1", (value.model,))
    if previous and previous["dimensions"] != len(value.vector):
        raise DawError("embedding_dimension_mismatch", "use an immutable model/revision identifier")
    with ws.db:
        ws.db.execute("INSERT INTO search_embedding VALUES(?,?,?,?,?) ON CONFLICT(document_id,model) "
                      "DO UPDATE SET fingerprint=excluded.fingerprint,dimensions=excluded.dimensions,vector=excluded.vector",
                      (value.document_id, value.model, value.fingerprint, len(value.vector), canonical(value.vector).decode()))
    return {"document_id": value.document_id, "model": value.model, "dimensions": len(value.vector)}


def search(ws, text="", *, family=None, feature=None, provider=None, format=None, min_level=0,
           limit=20, offset=0, include_historical=False, vector=None, model=None):
    if not 1 <= limit <= 100 or offset < 0 or min_level not in range(4):
        raise DawError("invalid_search_bounds")
    if family not in {None, "data", "artifact", "work", "resource", "forum", "claim"}:
        raise DawError("unknown_search_family")
    tokens = re.findall(r"[\w-]+", text, re.UNICODE)[:30]
    match = " AND ".join('"' + token.replace('"', '""') + '"' for token in tokens)
    conditions, params = ["d.level>=?"], [min_level]
    for field, value in (("family", family), ("provider", provider), ("format", format)):
        if value is not None:
            conditions.append(f"d.{field}=?")
            params.append(value)
    if not include_historical:
        conditions.append("NOT EXISTS(SELECT 1 FROM asset_revision a WHERE a.id=d.subject AND NOT EXISTS(SELECT 1 FROM current_asset c WHERE c.revision=a.id))")
    if feature is not None:
        conditions.append("EXISTS(SELECT 1 FROM feature_term f WHERE f.profile_id=d.record_id AND f.value=?)")
        params.append(feature)
    where = " AND ".join(conditions)
    if vector is not None:
        if (not model or not isinstance(vector, list) or not vector or len(vector) > 8192
                or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector)):
            raise DawError("invalid_embedding_query")
        norm = math.sqrt(sum(x*x for x in vector))
        if norm == 0 or not math.isfinite(norm):
            raise DawError("invalid_embedding_query")
        rows = ws.rows("SELECT d.*,e.vector FROM search_document d JOIN search_embedding e ON d.id=e.document_id "
                       "AND d.fingerprint=e.fingerprint WHERE " + where + " AND e.model=? AND e.dimensions=?",
                       params + [model, len(vector)])
        for row in rows:
            values = json.loads(row.pop("vector"))
            row["score"] = sum(a*b for a, b in zip(vector, values, strict=True)) / (norm * math.sqrt(sum(v*v for v in values)))
        rows.sort(key=lambda r: (-r["score"], r["id"]))
        total = len(rows)
        rows = rows[offset:offset + limit]
        method = "cosine over supplied model vectors; text argument is not a lexical filter"
    elif match:
        base = " FROM search_document d JOIN search_fts ON d.id=search_fts.id WHERE " + where + " AND search_fts MATCH ?"
        lexical_params = params + [match]
        if feature is None and len(tokens) == 1:
            # A single identifier also searches literal file contents.
            exact_base = " FROM search_document d WHERE " + where + " AND EXISTS(SELECT 1 FROM feature_term f WHERE f.profile_id=d.record_id AND f.value=?)"
            exact_params = params + [text.strip()]
            total = ws.one("SELECT count(*) AS n FROM (SELECT d.id" + base + " UNION SELECT d.id" + exact_base + ")",
                           lexical_params + exact_params)["n"]
            lexical = ws.rows("SELECT d.*,bm25(search_fts,0,5,3,1) AS score" + base + " ORDER BY score,d.id LIMIT ?", lexical_params + [offset + limit])
            exact = ws.rows("SELECT d.*,-1000000 AS score" + exact_base + " ORDER BY d.id LIMIT ?", exact_params + [offset + limit])
            combined = {r["id"]: r for r in lexical + exact}
            rows = sorted(combined.values(), key=lambda r: (r["score"], r["id"]))[offset:offset + limit]
            method = "exact source-label match plus SQLite FTS5 BM25"
        else:
            total = ws.one("SELECT count(*) AS n" + base, lexical_params)["n"]
            rows = ws.rows("SELECT d.*,bm25(search_fts,0,5,3,1) AS score" + base + " ORDER BY score,d.id LIMIT ? OFFSET ?", lexical_params + [limit, offset])
            method = "SQLite FTS5 BM25; literal query tokens joined with AND"
    else:
        total = ws.one("SELECT count(*) AS n FROM search_document d WHERE " + where, params)["n"]
        rows = ws.rows("SELECT d.*,0 AS score FROM search_document d WHERE " + where + " ORDER BY d.level DESC,d.id LIMIT ? OFFSET ?",
                       params + [limit, offset])
        method = "filtered local inventory"
    for row in rows:
        literal = feature if feature is not None else text.strip() if len(tokens) == 1 else None
        if literal is not None:
            row["content_matches"] = ws.rows("SELECT namespace,locator FROM feature_term WHERE profile_id=? AND value=? ORDER BY namespace,locator LIMIT 8", (row["record_id"], literal))
        row["content_is_untrusted_data"] = True
    return {"query": text, "method": method, "total": total, "offset": offset, "items": rows,
            "next_offset": offset + len(rows) if offset + len(rows) < total else None,
            "limitations": ["Profiles and apparent affordances are descriptive, not scientific approval",
                            "A missing search hit is not negative biological evidence; inspect indexing coverage"]}


def document(ws, key):
    row = ws.one("SELECT * FROM search_document WHERE id=?", (key,))
    if not row:
        raise DawError("unknown_search_document")
    return {**row, "body": read_json(ws.blob_path(row["body_blob"]))}
