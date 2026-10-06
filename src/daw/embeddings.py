"""Pinned local text embeddings for the search index (M1.8). No download, no service.

The default model, `hashing-ngram-v1`, is deterministic and needs no weights:
lower-cased word tokens and their boundary-marked character 3–5-grams are hashed
(BLAKE2b) into 512 signed dimensions with sublinear term weights, the title and
summary block and the detail block are l2-normalised separately, averaged and
normalised again. It captures shared spelling (inflections, British/American
variants, compounds, identifiers split differently) and nothing else: synonyms,
paraphrases and biology are invisible to it. Vectors depend only on the document
text, never on corpus statistics, so re-embedding is needed only when a document's
fingerprint changes. The model identifier carries the version and every parameter;
changing any of them is a new model, never a silent revision.

`sentence-transformers:<name>@<revision>` is accepted when that package and the
pinned revision are already present locally; it is loaded with
`local_files_only=True` and `trust_remote_code=False` unless the caller explicitly
allows a download. Exact-term search stays primary; vectors are an aid to recall.
"""
import hashlib
import math
import re

from daw.search import add_embedding, search
from daw.substrate_models import Embedding
from daw.util import DawError

HASHING = "hashing-ngram-v1"
STOPWORDS = frozenset(
    "a an and are as at be been but by can do does for from had has have how i if in into is it its may might "
    "no not of on or our so such than that the their then there these they this those to was we were what when "
    "which while who whom why will with would".split())


class HashingModel:
    """Deterministic character n-gram + word hashing model (`hashing-ngram-v1`)."""

    name = HASHING

    def __init__(self, dimensions=512, char_min=3, char_max=5, max_chars=20000):
        self.dimensions, self.char_min, self.char_max, self.max_chars = dimensions, char_min, char_max, max_chars
        self.id = (f"{HASHING}:dim={dimensions},char={char_min}-{char_max},word=1,hash=blake2b-8,"
                   f"weight=log1p,fields=title+summary|detail,max_chars={max_chars}")

    def card(self):
        return {"model": self.id, "kind": "feature hashing", "weights": "none (deterministic, no download)",
                "dimensions": self.dimensions, "captures": "shared words, word pieces and spelling variants",
                "does_not_capture": "synonyms, paraphrase, abbreviations without shared letters, biology",
                "corpus_dependence": "none; a vector depends only on its own text"}

    def features(self, text):
        counts = {}
        for word in re.findall(r"\w+", text[:self.max_chars].casefold()):
            if word in STOPWORDS or len(word) < 2:
                continue
            counts["w:" + word] = counts.get("w:" + word, 0) + 1
            marked = f"<{word}>"
            for n in range(self.char_min, self.char_max + 1):
                for i in range(len(marked) - n + 1):
                    gram = "c:" + marked[i:i + n]
                    counts[gram] = counts.get(gram, 0) + 1
        return counts

    def _vector(self, text):
        vector = [0.0] * self.dimensions
        for feature, count in self.features(text).items():
            h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
            vector[h % self.dimensions] += (1.0 if (h >> 63) & 1 else -1.0) * (1.0 + math.log(count))
        return _unit(vector)

    def embed(self, title, summary="", detail=""):
        parts = [v for v in (self._vector(f"{title}\n{summary}"), self._vector(detail)) if v]
        if not parts:
            raise DawError("empty_embedding_text", "no indexable words")
        combined = _unit([sum(values) for values in zip(*parts, strict=True)])
        if not combined:
            raise DawError("empty_embedding_text", "no indexable words")
        return combined

    def embed_query(self, text):
        return self.embed(text, "", text)


class SentenceTransformerModel:
    """Optional pinned sentence-transformers model; never downloads unless explicitly allowed."""

    def __init__(self, name, revision, *, allow_download=False):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise DawError("embedding_model_unavailable", "sentence-transformers is not installed") from e
        try:
            self.model = SentenceTransformer(name, revision=revision, local_files_only=not allow_download,
                                             trust_remote_code=False)
        except (OSError, ValueError) as e:
            raise DawError("embedding_model_unavailable",
                           f"{name}@{revision} is not available locally; downloads need explicit permission") from e
        self.id = f"sentence-transformers:{name}@{revision}"

    def card(self):
        return {"model": self.id, "kind": "sentence-transformers", "revision_pinned": True}

    def embed(self, title, summary="", detail=""):
        return _unit([float(x) for x in self.model.encode(f"{title}\n{summary}\n{detail}"[:20000])])

    def embed_query(self, text):
        return _unit([float(x) for x in self.model.encode(text)])


def _unit(vector):
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm and math.isfinite(norm) else []


_DEFAULT = HashingModel()
_LOADED = {}  # optional models stay loaded for the process (the web server embeds every vector query)


def load_model(spec=None, *, allow_download=False):
    """Resolve a model name or stored identifier. Only exact pinned identifiers are accepted."""
    if spec in (None, "", HASHING, _DEFAULT.id):
        return _DEFAULT
    if spec.startswith("sentence-transformers:"):
        name, _, revision = spec.removeprefix("sentence-transformers:").rpartition("@")
        if not name or not revision:
            raise DawError("unpinned_embedding_model", "use sentence-transformers:<name>@<revision>")
        if spec not in _LOADED:
            _LOADED[spec] = SentenceTransformerModel(name, revision, allow_download=allow_download)
        return _LOADED[spec]
    raise DawError("unknown_embedding_model", f"use {HASHING} or sentence-transformers:<name>@<revision>")


def embed_documents(ws, model=None, *, family=None, limit=None):
    """Embed current search documents whose fingerprint has no vector for this model. Caller holds the writer.

    Reads the compact text that `index_document` stored (title, summary, FTS detail); the
    fingerprint check in `add_embedding` keeps a vector bound to the exact document version.
    """
    model = model if hasattr(model, "embed") else load_model(model)
    if limit is not None and limit < 1:
        raise DawError("invalid_embedding_bound")
    where, params = "", [model.id]
    if family:
        where, params = " AND d.family=?", [model.id, family]
    pending = ws.rows("SELECT d.id,d.fingerprint,d.title,d.summary,f.detail FROM search_document d "
                      "LEFT JOIN search_fts f ON f.id=d.id LEFT JOIN search_embedding e ON e.document_id=d.id AND e.model=? "
                      "WHERE (e.fingerprint IS NULL OR e.fingerprint!=d.fingerprint)" + where + " ORDER BY d.id"
                      + (" LIMIT ?" if limit else ""), params + ([limit] if limit else []))
    embedded, skipped = [], []
    for row in pending:
        try:
            vector = model.embed(row["title"], row["summary"], row["detail"] or "")
        except DawError as e:
            skipped.append({"document": row["id"], "reason": e.reason})
            continue
        add_embedding(ws, Embedding(document_id=row["id"], fingerprint=row["fingerprint"], model=model.id, vector=vector))
        embedded.append(row["id"])
    return {**coverage(ws, model.id, family=family), "model": model.id, "embedded": len(embedded),
            "skipped": skipped, "family": family, "embedded_documents": embedded[:50]}


def coverage(ws, model_id, *, family=None):
    where, params = ("WHERE d.family=?", [model_id, family]) if family else ("", [model_id])
    row = ws.one("SELECT count(*) AS documents, count(e.document_id) AS current FROM search_document d "
                 "LEFT JOIN search_embedding e ON e.document_id=d.id AND e.model=? AND e.fingerprint=d.fingerprint "
                 + where, params)
    return {"documents": row["documents"], "with_current_vector": row["current"],
            "without_current_vector": row["documents"] - row["current"]}


def vector_search(ws, text, *, model=None, family=None, limit=20, offset=0, **filters):
    """Cosine search with the query embedded by the same pinned model. Works on read-only workspaces."""
    if not text.strip():
        raise DawError("empty_vector_query")
    model = model if hasattr(model, "embed") else load_model(model)
    vector = model.embed_query(text)
    if not vector:
        raise DawError("empty_embedding_text", "no indexable words in the query")
    result = search(ws, "", family=family, limit=limit, offset=offset, vector=vector, model=model.id, **filters)
    result.update(query=text, model=model.id, coverage=coverage(ws, model.id, family=family))
    result["method"] = f"cosine over {model.id} vectors; the query text is embedded, not matched literally"
    result["limitations"] = result["limitations"] + [
        "Vector similarity is a recall aid; exact-term search remains the primary retrieval",
        "Documents without a current vector for this model are not searched; see coverage"]
    return result
