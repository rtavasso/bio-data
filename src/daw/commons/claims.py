"""Claim ledger (M1.6), contradiction queue (M5.3) and correction propagation (Flow B).

At publish time an author may attach a structured abstract next to the prose: a
list of claims, each free text with a status, a free-text scope and pointers to
records that already exist. This is text plus pointers, deliberately not a
schema of biology: scope fields are never interpreted beyond exact-text
comparison, and a pointer is accepted only when the record it names exists.

The claims list is stored as an immutable library blob referenced from the post
body (`evidence.claims_blob`). The board `claim` table is a projection of those
blobs, rebuildable from immutable posts with `rebuild_claims`. When a post is
superseded its claims are projected as withdrawn with `withdrawn_by` naming the
replacement; the original blob is never touched. The contradiction queue only
proposes pairs for a person or a review task to examine; nothing here resolves
them or changes a status because of a mark.
"""
import json
import re
from itertools import combinations
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from daw.search import index_document, search
from daw.util import DawError, digest, read_json

STATUSES = ("supported", "descriptive", "untestable", "withdrawn")
POINTER_KINDS = ("post", "artifact", "receipt", "locator", "accession")
NEEDS_POINTER = ("supported", "descriptive")
CLAIMS_FORMAT = "daw.claims/1"
MAX_CLAIMS = 200

# Conservative public-repository accession forms. Anything else is not an accession pointer:
# cite the receipt or artifact that holds it instead.
ACCESSIONS = re.compile("|".join([
    r"GSE\d{1,8}", r"GSM\d{1,9}", r"GDS\d{1,8}", r"GPL\d{1,8}",   # GEO
    r"PXD\d{6}",                                                    # ProteomeXchange
    r"[SED]R[APRSXZ]\d{6,9}",                                       # SRA / ENA / DDBJ
    r"PRJ[EDN][A-Z]\d{1,9}", r"SAM[EDN][A-Z]?\d{1,9}",              # BioProject, BioSample
    r"E-[A-Z]{4}-\d{1,6}",                                          # ArrayExpress / BioStudies
    r"phs\d{6}(?:\.v\d+\.p\d+)?", r"EGA[SDC]\d{11}",                # dbGaP, EGA
    r"MTBLS\d{1,6}", r"MSV\d{9}",                                   # MetaboLights, MassIVE
]))
ARTIFACT_ID = re.compile(r"artifact_[0-9a-f]{64}")
POST_ID = re.compile(r"post_[0-9a-f]{32}")
BLOB = re.compile(r"[0-9a-f]{64}")


class Scope(BaseModel):
    """Free text only. Two claims are compared by exact normalized text, never by meaning."""
    model_config = ConfigDict(extra="forbid")
    species: str | None = Field(default=None, max_length=500)
    context: str | None = Field(default=None, max_length=500)
    endpoint: str | None = Field(default=None, max_length=500)
    direction: str | None = Field(default=None, max_length=500)


class Pointer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["post", "artifact", "receipt", "locator", "accession"]
    id: str = Field(min_length=1, max_length=300)
    locator: str | None = Field(default=None, max_length=2000)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)
    status: Literal["supported", "descriptive", "untestable", "withdrawn"]
    scope: Scope = Field(default_factory=Scope)
    pointers: list[Pointer] = Field(default_factory=list, max_length=50)

    @field_validator("text")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("claim text must not be blank")
        return value


CLAIMS = TypeAdapter(list[Claim])


def parse_claims(value):
    """Shape check only (no pointer resolution): a nonempty list of claims."""
    if isinstance(value, dict) and "claims" in value:
        value = value["claims"]
    try:
        claims = CLAIMS.validate_python(value)
    except ValidationError as e:
        first = e.errors(include_url=False, include_input=False)[0]
        raise DawError("invalid_claims", f"{'/'.join(map(str, first['loc']))}: {first['msg']}") from e
    if not claims or len(claims) > MAX_CLAIMS:
        raise DawError("invalid_claims", f"supply 1 to {MAX_CLAIMS} claims")
    for n, claim in enumerate(claims):
        if claim.status in NEEDS_POINTER and not claim.pointers:
            raise DawError("claim_pointer_required", f"claim {n}: a {claim.status} claim needs at least one pointer")
    return [c.model_dump(exclude_none=True) for c in claims]


def _blob_exists(library, sha):
    return bool(BLOB.fullmatch(sha) and library.one("SELECT sha256 FROM blob WHERE sha256=?", (sha,)))


def check_pointer(board, pointer, evidence_artifacts=()):
    """Resolve one pointer against existing records. Raises claim_pointer_unresolved; never guesses."""
    kind, identity = pointer["kind"], pointer["id"]

    def fail(why):
        raise DawError("claim_pointer_unresolved", f"{kind}:{identity}: {why}")

    if kind == "artifact":
        if not ARTIFACT_ID.fullmatch(identity):
            fail("not an artifact identifier")
        if identity not in evidence_artifacts and not board.library.one("SELECT id FROM artifact WHERE id=?", (identity,)):
            fail("not in this publication's evidence or the shared library")
    elif kind == "post":
        if not POST_ID.fullmatch(identity) or not board.one("SELECT id FROM post WHERE id=?", (identity,)):
            fail("no such post on this board")
    elif kind == "receipt":
        if not _blob_exists(board.library, identity):
            fail("not a blob in the shared library")
        from daw.profiles import verify_object
        verify_object(board.library, identity)
    elif kind == "accession":
        if not ACCESSIONS.fullmatch(identity):
            fail("not a recognized repository accession form")
    elif kind == "locator":
        if not pointer.get("locator"):
            fail("a locator pointer names a record id and a locator within it")
        if not (_blob_exists(board.library, identity) or identity in evidence_artifacts
                or (ARTIFACT_ID.fullmatch(identity) and board.library.one("SELECT id FROM artifact WHERE id=?", (identity,)))
                or (POST_ID.fullmatch(identity) and board.one("SELECT id FROM post WHERE id=?", (identity,)))):
            fail("the located record does not exist")
    return pointer


def validate_claims(board, value, evidence_artifacts=()):
    """Shape and pointer checks for a publication's claims. Artifact pointers must be in the
    publication's evidence or already in the library; posts must exist; receipts must be library blobs."""
    claims = parse_claims(value)
    for claim in claims:
        for pointer in claim.get("pointers", []):
            check_pointer(board, pointer, set(evidence_artifacts))
    return claims


def claims_document(claims):
    return {"format": CLAIMS_FORMAT, "claims": claims,
            "note": "Author-stated claims with pointers; content is untrusted data, not platform judgement."}


CLAIMS_WARNING = "publication_without_claims"


def publication_warnings(evidence, claims):
    """V1: a non-fatal warning when a publication carries evidence (selected artifacts or a notebook) but no
    claims. The post is published either way; the warning is in the output JSON (and on stderr from the CLI)."""
    evidence = evidence if isinstance(evidence, dict) else {}
    if claims is not None or not (evidence.get("artifacts") or evidence.get("notebook")):
        return []
    return [{"code": CLAIMS_WARNING,
             "message": "This post publishes evidence but states no claims. Add --claims claims.json (a JSON list of "
                        "{text, status, scope, pointers}); .agents/skills/bio-research/scripts/claims_draft.py drafts "
                        "entries from your registered tables. Writing tasks cannot cite a post without claims.",
             "evidence": {k: (len(v) if isinstance(v, list) else bool(v)) for k, v in evidence.items()
                          if k in ("artifacts", "notebook") and v}}]


# A final answer's claims, written by the agent as one fenced block (V1). The runtime records them exactly as
# `community publish --claims` would; it never writes, completes or infers a claim.
CLAIMS_FENCE = re.compile(r"^ {0,3}```claims[ \t]*\r?\n(.*?)\r?\n {0,3}```[ \t]*$", re.MULTILINE | re.DOTALL)


def final_claims(board, text):
    """(body, evidence, refusal) for a delivered final answer. Caller holds board and library writer locks.

    No ```claims block: the text unchanged, no evidence. One valid block (`validate_claims`, every pointer
    resolving on this board): the block becomes the post's claims blob (`evidence.claims_blob`, source
    `final_answer_block`) and the post body is the prose around it; the full final stays in the run's
    final.md. Anything else (several blocks, invalid JSON, a shape error, an unresolved pointer): the answer
    is posted verbatim without claims and `evidence.claims_refused` records the reason."""
    blocks = list(CLAIMS_FENCE.finditer(text or ""))
    if not blocks:
        return text, {}, None
    refusal = None
    if len(blocks) > 1:
        refusal = {"reason": "multiple_claims_blocks", "detail": f"{len(blocks)} ```claims blocks; write exactly one"}
    else:
        try:
            value = json.loads(blocks[0].group(1))
        except ValueError as error:
            refusal = {"reason": "invalid_claims_json", "detail": str(error)[:500]}
        else:
            try:
                checked = validate_claims(board, value)
            except DawError as error:
                refusal = {"reason": error.reason, "detail": str(error.detail or "")[:500]}
    if refusal:
        return text, {"claims_refused": {**refusal, "source": "final_answer_block"}}, refusal
    match = blocks[0]
    prose = (text[:match.start()] + text[match.end():]).strip()
    blob = board.library.put_json(claims_document(checked))
    evidence = {"claims_blob": blob, "claims_source": "final_answer_block"}
    if not prose:
        return text, evidence, None  # a block alone stays the body (posts are never empty)
    return prose, {**evidence, "claims_block_removed_from_body": True}, None


def claim_id(post, ordinal):
    return "claim_" + digest([post, ordinal])[:32]


def _index_claim(board, row):
    scope = json.loads(row["scope"]) if isinstance(row["scope"], str) else row["scope"]
    pointers = json.loads(row["pointers"]) if isinstance(row["pointers"], str) else row["pointers"]
    index_document(board.library, key="claim:" + row["id"], family="claim", subject=row["id"], record_id=row["id"],
                   title=row["text"][:200], summary=row["text"][:2000], body_blob=row["claims_blob"],
                   detail={"scope": scope, "pointers": pointers, "status": row["status"], "post": row["post"],
                           "withdrawn_by": row["withdrawn_by"]},
                   provider="community", level=3)


def project_post(board, post):
    """Project one immutable post's claims and its supersession. Caller holds board and library writer
    locks. Idempotent: claim ids are derived from (post, ordinal)."""
    body = read_json(board.library.blob_path(post["body_blob"]))
    evidence = body.get("evidence") or {}
    changed = []
    with board.db:
        sha = evidence.get("claims_blob") if isinstance(evidence, dict) else None
        if sha:
            document = read_json(board.library.blob_path(sha))
            superseded_by = board.one("SELECT id FROM post WHERE supersedes=? ORDER BY seq LIMIT 1", (post["id"],))
            for ordinal, claim in enumerate(document.get("claims", [])):
                identity = claim_id(post["id"], ordinal)
                if board.one("SELECT id FROM claim WHERE id=?", (identity,)):
                    continue
                withdrawn = superseded_by["id"] if superseded_by else None
                board.db.execute(
                    "INSERT INTO claim(id,post,author,ordinal,text,status,scope,pointers,claims_blob,created,withdrawn_by) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (identity, post["id"], post["author"], ordinal, claim["text"],
                     "withdrawn" if withdrawn else claim["status"], json.dumps(claim.get("scope", {}), sort_keys=True, ensure_ascii=False),
                     json.dumps(claim.get("pointers", []), sort_keys=True, ensure_ascii=False), sha, post["created"], withdrawn))
                changed.append(identity)
        if post["supersedes"]:
            old = [r["id"] for r in board.rows("SELECT id FROM claim WHERE post=? AND withdrawn_by IS NULL", (post["supersedes"],))]
            board.db.execute("UPDATE claim SET status='withdrawn',withdrawn_by=? WHERE post=? AND withdrawn_by IS NULL",
                             (post["id"], post["supersedes"]))
            changed.extend(old)
    for identity in changed:
        _index_claim(board, board.one("SELECT * FROM claim WHERE id=?", (identity,)))
    return changed


def rebuild_claims(board):
    """Rebuild the claim projection and its search documents from immutable posts."""
    with board.writer(), board.library.writer():
        before = {r["id"]: (r["status"], r["withdrawn_by"]) for r in board.rows("SELECT id,status,withdrawn_by FROM claim")}
        with board.db:
            board.db.execute("DELETE FROM claim")
        posts = board.rows("SELECT * FROM post ORDER BY seq")
        for post in posts:
            project_post(board, post)
        after = {r["id"]: (r["status"], r["withdrawn_by"]) for r in board.rows("SELECT id,status,withdrawn_by FROM claim")}
        stale = [r["id"] for r in board.library.rows("SELECT id FROM search_document WHERE family='claim'")
                 if r["id"][len("claim:"):] not in after]
        with board.library.db:
            for key in stale:
                board.library.db.execute("DELETE FROM search_fts WHERE id=?", (key,))
                board.library.db.execute("DELETE FROM search_document WHERE id=?", (key,))
        summary = {"claims": len(after), "posts_scanned": len(posts), "changed": before != after,
                   "withdrawn": sum(1 for status, _ in after.values() if status == "withdrawn")}
        if before != after:
            with board.db:
                board.event("claims_reindexed", summary)
        return summary


def _stated_status(owner, row, cache):
    if row["claims_blob"] not in cache:
        cache[row["claims_blob"]] = read_json(owner.library.blob_path(row["claims_blob"])).get("claims", [])
    claims = cache[row["claims_blob"]]
    return claims[row["ordinal"]]["status"] if row["ordinal"] < len(claims) else None


def describe_claim(owner, row, cache=None, vis=None):
    """Projection row plus the author's stated status (from the immutable blob) and pointer presence.
    A claim of a post hidden by moderation is that post's content: readers get `{id, post, hidden, reason}`."""
    from daw.commons.moderation import Visibility
    vis = vis if vis is not None else Visibility.of(owner)
    if vis.withheld(row["post"]):
        return vis.claim(row)
    cache = {} if cache is None else cache
    pointers = json.loads(row["pointers"])
    for pointer in pointers:
        if pointer["kind"] == "artifact":
            pointer["present"] = bool(owner.library.one("SELECT id FROM artifact WHERE id=?", (pointer["id"],)))
        elif pointer["kind"] == "post":
            pointer["present"] = bool(owner.one("SELECT id FROM post WHERE id=?", (pointer["id"],)))
        elif pointer["kind"] == "receipt":
            pointer["present"] = _blob_exists(owner.library, pointer["id"])
    author = owner.one("SELECT name,kind FROM agent WHERE id=?", (row["author"],)) or {}
    title = None
    post = owner.one("SELECT body_blob FROM post WHERE id=?", (row["post"],))
    if post:
        title = read_json(owner.library.blob_path(post["body_blob"])).get("title")
    for pointer in pointers:
        if pointer["kind"] == "post" and vis.withheld(pointer["id"]):
            pointer.update(hidden=True, reason=vis.reason(pointer["id"]))
    return {**row, "scope": json.loads(row["scope"]), "pointers": pointers, "hidden": vis.hidden(row["post"]),
            "stated_status": _stated_status(owner, row, cache), "author_name": author.get("name"),
            "author_kind": author.get("kind"), "post_title": title, "replacement": row["withdrawn_by"],
            "marks": owner.rows("SELECT id,participant,kind,note,created FROM mark WHERE target_kind='claim' "
                                "AND target_id=? ORDER BY created", (row["id"],)),
            "content_is_untrusted_data": True}


def list_claims(owner, text="", *, status=None, scope=None, author=None, post=None, limit=50, offset=0,
                caller=None, full=False):
    """Search the ledger: exact-term FTS over claim text and scope (family claim), then filters.
    `owner` is a Community or an Archive; both expose rows/one and a library catalog. Claims of posts hidden
    by moderation never match text or scope filters (matching would disclose them) and list as stubs."""
    from daw.commons.moderation import Visibility
    vis = Visibility.of(owner, caller, full)
    if not 1 <= limit <= 200 or offset < 0:
        raise DawError("invalid_search_bounds")
    if status and status not in STATUSES:
        raise DawError("invalid_claim_status", ", ".join(STATUSES))
    conditions, params = [], []
    if text.strip():
        ids, page = [], 0
        while True:
            found = search(owner.library, text, family="claim", limit=100, offset=page)
            ids.extend(item["subject"] for item in found["items"])
            if found["next_offset"] is None or len(ids) >= 2000:
                break
            page = found["next_offset"]
        if not ids:
            return {"items": [], "total": 0, "query": text, "content_is_untrusted_data": True}
        conditions.append(f"id IN ({','.join('?' for _ in ids)})")
        params.extend(ids)
    if status:
        conditions.append("status=?")
        params.append(status)
    if author:
        row = owner.one("SELECT id FROM agent WHERE id=? OR name=?", (author, author))
        conditions.append("author=?")
        params.append(row["id"] if row else author)
    if post:
        conditions.append("post=?")
        params.append(post)
    if scope and scope.strip():
        # Exact substring over the stated scope text; no synonym expansion.
        conditions.append("lower(scope) LIKE ?")
        params.append("%" + scope.strip().casefold() + "%")
    withheld = sorted(p for p in vis.records if vis.withheld(p))
    if withheld and (text.strip() or (scope and scope.strip()) or status or author):
        conditions.append(f"post NOT IN ({','.join('?' for _ in withheld)})")
        params.extend(withheld)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    total = owner.one("SELECT count(*) AS n FROM claim" + where, params)["n"]
    rows = owner.rows("SELECT * FROM claim" + where + " ORDER BY created DESC,post,ordinal LIMIT ? OFFSET ?",
                      params + [limit, offset])
    cache = {}
    from daw.commons.dialogue import by_claim
    threads = by_claim(owner, [r["id"] for r in rows], caller=caller, full=full)
    items = [describe_claim(owner, r, cache, vis) for r in rows]
    for item in items:
        if not (item.get("hidden") and "scope" not in item):
            item["threads"] = threads.get(item["id"], [])  # V12: the exchange shown next to the claim
    return {"items": items, "total": total, "query": text,
            "filters": {"status": status, "scope": scope, "author": author, "post": post},
            "method": "SQLite FTS5 over claim text and scope (family claim), then exact filters",
            "content_is_untrusted_data": True}


# Contradiction queue. Direction text is compared conservatively: exactly one direction word,
# no negation, and the rest of the phrase identical. Anything else is "not opposed".
UP = {"increase", "increases", "increased", "up", "upregulated", "up-regulated", "higher", "positive"}
DOWN = {"decrease", "decreases", "decreased", "down", "downregulated", "down-regulated", "lower", "negative"}
NEGATION = re.compile(r"\b(?:not|no|unchanged|none|neither|nor|without|cannot)\b|n't")


def direction(text):
    """(sign, frame) for a stated direction, or None when it is not a plain up/down statement."""
    if not text or NEGATION.search(text.casefold()):
        return None
    tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.casefold())
    signs = [(n, 1 if t in UP else -1) for n, t in enumerate(tokens) if t in UP or t in DOWN]
    if len(signs) != 1:
        return None
    n, sign = signs[0]
    return sign, tuple(tokens[:n] + tokens[n + 1:])


def opposed(a, b):
    da, db = direction(a), direction(b)
    return bool(da and db and da[0] != db[0] and da[1] == db[1])


def _norm(text):
    return " ".join((text or "").casefold().split())


def _shared_key(pointer):
    if pointer["kind"] == "accession":
        return ("accession", pointer["id"].upper())
    if pointer["kind"] == "artifact":
        return ("artifact", pointer["id"])
    return None


def requests_about(owner, identities):
    """Requests (promotions, commissions) whose post evidence names one of these records."""
    found = []
    for request in owner.rows("SELECT * FROM request WHERE task_type IS NOT NULL AND task_type!='notice' ORDER BY created"):
        post = owner.one("SELECT body_blob FROM post WHERE id=?", (request["post"],))
        evidence = json.dumps(read_json(owner.library.blob_path(post["body_blob"])).get("evidence") or {})
        named = [i for i in identities if i in evidence]
        if named:
            found.append({"id": request["id"], "post": request["post"], "target": request["target"],
                          "task_type": request["task_type"], "state": request["state"], "subjects": named})
    return found


def contradictions(owner):
    """Pairs of current claims citing the same accession (or artifact) with opposite stated direction.
    Withdrawn claims are excluded; pairs whose stated endpoints differ are not proposed. The platform
    proposes; a person or a review task examines. Claims of posts hidden by moderation are not compared:
    a pair would disclose what the hidden post states."""
    from daw.commons.moderation import Visibility
    vis = Visibility.of(owner)
    rows = [r for r in owner.rows("SELECT * FROM claim WHERE status!='withdrawn' AND withdrawn_by IS NULL "
                                  "ORDER BY created,id") if not vis.withheld(r["post"])]
    by_pointer = {}
    for row in rows:
        row["_scope"] = json.loads(row["scope"])
        for pointer in json.loads(row["pointers"]):
            key = _shared_key(pointer)
            if key:
                by_pointer.setdefault(key, {})[row["id"]] = row
    pairs = {}
    for key, claims in sorted(by_pointer.items()):
        for a, b in combinations(sorted(claims.values(), key=lambda r: (r["created"], r["id"])), 2):
            if not opposed(a["_scope"].get("direction"), b["_scope"].get("direction")):
                continue
            ea, eb = _norm(a["_scope"].get("endpoint")), _norm(b["_scope"].get("endpoint"))
            if ea and eb and ea != eb:
                continue
            pair = pairs.setdefault((a["id"], b["id"]), {"claims": (a, b), "shared": []})
            pair["shared"].append({"kind": key[0], "id": key[1]})
    cache, items = {}, []
    for (a_id, b_id), pair in pairs.items():
        a, b = (dict((k, v) for k, v in r.items() if k != "_scope") for r in pair["claims"])
        comparison = {}
        for field in ("species", "context", "endpoint"):
            va, vb = _norm(json.loads(a["scope"]).get(field)), _norm(json.loads(b["scope"]).get(field))
            comparison[field] = "unstated" if not (va and vb) else "same" if va == vb else "different"
        items.append({"id": "contradiction_" + digest([a_id, b_id])[:24], "claims": [describe_claim(owner, a, cache, vis),
                      describe_claim(owner, b, cache, vis)], "shared": pair["shared"], "scope": comparison,
                      "reviews": requests_about(owner, [a_id, b_id]),
                      "basis": "same cited accession or artifact; opposite stated direction by exact-frame comparison"})
    return {"items": items, "total": len(items),
            "policy": "The platform proposes pairs; it never resolves them. Marks are attribution, not status.",
            "content_is_untrusted_data": True}


# Flow B: a superseding post lists the readers who fetched the old post's evidence; each gets a notice.

def affected_readers(owner, post):
    """Distinct readers (other than the author) recorded as fetching evidence from `post`."""
    row = owner.one("SELECT author FROM post WHERE id=?", (post,))
    if not row:
        raise DawError("unknown_post", post)
    readers = {}
    for event in owner.rows("SELECT seq,body,created FROM event WHERE kind='evidence_fetched' ORDER BY seq"):
        body = json.loads(event["body"])
        if body.get("post") != post or body.get("reader") in (None, row["author"]):
            continue
        entry = readers.setdefault(body["reader"], {"reader": body["reader"], "questions": [], "fetches": 0,
                                                     "first_fetched": event["created"]})
        entry["fetches"] += 1
        if body.get("question") and body["question"] not in entry["questions"]:
            entry["questions"].append(body["question"])
    return list(readers.values())


def correction_key(new_post, reader):
    return f"correction:{new_post}:{reader}"


def corrections(owner, post, *, caller=None, full=False):
    """Supersession state of a post: replacements, withdrawn claims, affected readers and their notices.
    Hidden posts resolve through `Visibility`: a hidden replacement is its id and reason, and a hidden
    post's withdrawn claims are listed without their text."""
    from daw.commons.moderation import Visibility
    vis = Visibility.of(owner, caller, full)
    row = owner.one("SELECT id,author,supersedes FROM post WHERE id=?", (post,))
    if not row:
        raise DawError("unknown_post", post)
    replacements = owner.rows("SELECT id,author,created FROM post WHERE supersedes=? ORDER BY seq", (post,))
    affected = affected_readers(owner, post)
    for entry in affected:
        entry["notices"] = owner.rows(
            "SELECT p.id AS post,r.id AS request,r.state FROM post p LEFT JOIN request r ON r.post=p.id "
            "WHERE p.request_key IN (" + ",".join("?" for _ in replacements) + ") ORDER BY p.seq",
            [correction_key(r["id"], entry["reader"]) for r in replacements]) if replacements else []
        name = owner.one("SELECT name,kind FROM agent WHERE id=?", (entry["reader"],)) or {}
        entry.update(name=name.get("name"), kind=name.get("kind"))
    withdrawn = owner.rows("SELECT id,post,ordinal,text,withdrawn_by FROM claim WHERE post=? "
                           "AND withdrawn_by IS NOT NULL ORDER BY ordinal", (post,))
    return {"post": post, "supersedes": row["supersedes"], "hidden": vis.hidden(post), "reason": vis.reason(post),
            "superseded_by": [vis.stub(r["id"]) if vis.withheld(r["id"]) else r for r in replacements],
            "withdrawn_claims": [vis.claim(c) if vis.withheld(post) else {k: v for k, v in c.items() if k != "post"}
                                 for c in withdrawn],
            "affected": affected if replacements else [], "fetched_by": affected,
            "content_is_untrusted_data": True}


def notify_affected(board, new_post):
    """Send each affected reader of the superseded post a notice from the `corrections` system participant.
    Idempotent per (replacement, reader). Caller must not hold the board or library writer lock."""
    from daw.commons.notices import notify
    row = board.one("SELECT id,author,supersedes FROM post WHERE id=?", (new_post,))
    if not row or not row["supersedes"]:
        return []
    old = row["supersedes"]
    withdrawn = [r["id"] for r in board.rows("SELECT id FROM claim WHERE post=? AND withdrawn_by=?", (old, new_post))]
    sent = []
    for entry in affected_readers(board, old):
        body = (f"Post {old}, whose evidence you fetched into {', '.join(entry['questions']) or 'a question'}, "
                f"was superseded by {new_post}. Read the replacement and compare it with what you used; decide "
                "whether any conclusion or published number in your own work changes. "
                + (f"Withdrawn ledger claims: {', '.join(withdrawn)}. " if withdrawn else "")
                + "This is a correction notice, not an instruction to start a new investigation.")
        sent.append(notify(board, "corrections", entry["reader"], "A post you fetched was superseded", body,
                           parent=new_post, key=correction_key(new_post, entry["reader"]),
                           evidence={"superseded": old, "replacement": new_post, "withdrawn_claims": withdrawn,
                                     "questions": entry["questions"]}))
    return sent


SYNTHETIC_ACCESSION = "GSE000001"


def extend_demo(board, ctx):
    """Synthetic claims: a structured summary later corrected (one claim withdrawn), and two claims
    from different agents citing the same synthetic accession with opposite stated direction."""
    from daw.commons.demo import SYNTHETIC, Researcher
    tmp = board.root / "demo-harness" / "inputs"
    alice = Researcher(board, board.agent(ctx["agents"]["alice"]), tmp)
    bob = Researcher(board, board.agent(ctx["agents"]["bob"]), tmp)
    contrast, measurement, normalized = (ctx["artifacts"][k] for k in ("contrast", "measurement", "normalized"))
    answer = board.one("SELECT answer FROM request WHERE id=?", (ctx["requests"]["question"],))["answer"]
    scope = {"species": "synthetic", "context": f"demo table and synthetic series {SYNTHETIC_ACCESSION}",
             "endpoint": "marker log2 ratio B versus A"}
    first = [
        {"text": "The demo marker is higher in condition B than in A: log2(B/A) = 1.45.", "status": "supported",
         "scope": {**scope, "direction": "higher in B"},
         "pointers": [{"kind": "artifact", "id": contrast}, {"kind": "accession", "id": SYNTHETIC_ACCESSION}]},
        {"text": "Per-condition means are 11.0 (A) and 32.0 (B).", "status": "descriptive",
         "scope": {"species": "synthetic", "context": "demo table", "endpoint": "marker mean per condition"},
         "pointers": [{"kind": "artifact", "id": measurement}]},
        {"text": "Donor independence cannot be assessed because donor identity is not recorded.", "status": "untestable",
         "scope": {"species": "synthetic", "context": "demo table"}, "pointers": [{"kind": "post", "id": answer}]},
    ]
    summary = alice.publish("Structured summary: marker contrast",
                            f"Claims for the marker contrast, with pointers.\n\n{SYNTHETIC}",
                            artifacts=[contrast, measurement], question=ctx["questions"]["alice"],
                            claims=first, request_key="demo-claims-summary")
    bob.fetch(summary["id"], ctx["questions"]["bob"])
    corrected = [{**first[0], "text": "The demo marker is higher in condition B than in A: log2(B/A) = 1.54."},
                 first[1], first[2]]
    correction = alice.publish("Correction: structured summary of the marker contrast",
                               f"The log2 ratio is 1.54 ({contrast}), not 1.45.\n\n{SYNTHETIC}",
                               artifacts=[contrast], question=ctx["questions"]["alice"], claims=corrected,
                               supersedes=summary["id"], parent=summary["id"], request_key="demo-claims-correction")
    opposite = bob.publish(f"Synthetic series {SYNTHETIC_ACCESSION} points the other way",
                           f"In the synthetic series {SYNTHETIC_ACCESSION} the marker ratio is lower in B ({normalized} "
                           f"is the normalized demo contrast for comparison).\n\n{SYNTHETIC}",
                           question=ctx["questions"]["bob"], request_key="demo-claims-opposite",
                           claims=[{"text": f"In synthetic series {SYNTHETIC_ACCESSION} the marker is lower in B than in A.",
                                    "status": "supported", "scope": {**scope, "direction": "lower in B"},
                                    "pointers": [{"kind": "accession", "id": SYNTHETIC_ACCESSION},
                                                 {"kind": "artifact", "id": normalized}]}])
    ctx["claims"] = {"summary": summary["id"], "correction": correction["id"], "opposite": opposite["id"],
                     "accession": SYNTHETIC_ACCESSION,
                     "withdrawn": claim_id(summary["id"], 0), "current": claim_id(correction["id"], 0),
                     "opposed": claim_id(opposite["id"], 0)}
