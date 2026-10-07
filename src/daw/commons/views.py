"""Observatory read models (M8.1, M4.1, M4.5): threads, posts, artifacts, participants, requests, runs.

Every function takes a read-only `Archive` and returns JSON-ready dicts; nothing here writes.
Board-only views (the thread index) are cached in-process keyed by `archive.sequence()`, and
decoded post bodies by their content hash; no cache entry is authoritative and every view can be
recomputed from the archive. Reader workspaces change without board events, so views that read
them (fetches, reuse, questions holding an artifact) are computed on each request.

Edges are recorded relations only: a post's evidence list, `published`/`evidence_fetched` board
events, `question_artifact` rows, derivation inputs, parent/supersedes links and request rows.
Numbers in a post are reported by the write-up number checker (`daw.commons.checks.post_numbers`): a
pointer at the number is verified against its record or shown as unverified; a number covered only by
the post's evidence list is post-scoped; one without either is unpointed, never attached to a guess.
Refused write-ups (a recorded `writeup_check` verdict) are placeholders on every card and page here.
"""
import difflib
import json
import re
from collections import Counter, OrderedDict
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from daw.artifacts import artifact_info, provenance, reuse_links
from daw.catalog import Workspace
from daw.commons.moderation import Visibility
from daw.commons.participants import describe
from daw.commons.participation import comment_target
from daw.community import SEARCH_FAMILIES, evidence_summary, find, posts_naming
from daw.util import DawError, read_json

ARTIFACT_ID = re.compile(r"\bartifact_[0-9a-f]{64}\b")
POST_ID = re.compile(r"\bpost_[0-9a-f]{32}\b")
# A number is a standalone numeric token: identifiers such as PMP22, log2 or GSE1234 are not numbers.
NUMBER = re.compile(r"(?<![\w.])[-+−]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?(?![\w])")
LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]|#+)\s")
SNIPPET = 300
THREAD_SORTS = ("recent", "activity")
SEARCH_PAGES = 10            # forum text search considers at most 10 x 100 hits before filtering
_INDEX: "OrderedDict[tuple, dict]" = OrderedDict()
_INDEX_SIZE = 8


@lru_cache(maxsize=4096)
def _content(library_root, sha):
    """Decoded post body by content hash. Immutable bytes, so the cache never goes stale."""
    return read_json(Workspace.blob_path(SimpleNamespace(root=Path(library_root)), sha))


def content(view, sha):
    return _content(str(view.library.root), sha)


def _jsonish(value, default):
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------- participants

def participants_by_id(view):
    return {row["id"]: describe(row) for row in view.rows("SELECT * FROM agent")}


def resolve_participant(view, identity):
    return view.participant(identity)["id"] if identity else None


def is_operator(caller):
    return bool(caller) and caller.get("kind") == "operator"


# ---------------------------------------------------------------------------- moderation

def hidden_posts(view):
    """Current hide flags from the moderation projection. Bytes are never deleted; unhide restores display.
    Read models resolve what a caller may see through `daw.commons.moderation.Visibility`, not this map."""
    return Visibility.of(view).records


def visibility(view, caller=None, full=False):
    return Visibility.of(view, caller, full)


# ---------------------------------------------------------------------------- thread index

def thread_index(view):
    """Every post with decoded content, thread membership and corrections; cached per event sequence."""
    key = (str(view.root), view.sequence())
    if key in _INDEX:
        _INDEX.move_to_end(key)
        return _INDEX[key]
    people = participants_by_id(view)
    posts = OrderedDict()
    for row in view.rows("SELECT * FROM post ORDER BY seq"):
        body = content(view, row["body_blob"])
        posts[row["id"]] = {**row, "content": body}
    children, superseded_by = {}, {}
    for pid, row in posts.items():
        if row["parent"]:
            children.setdefault(row["parent"], []).append(pid)
        if row["supersedes"]:
            superseded_by.setdefault(row["supersedes"], []).append(pid)

    def root_of(pid):
        seen = set()
        while pid not in seen:
            seen.add(pid)
            row = posts[pid]
            # A correction published without a parent belongs to the thread of the post it supersedes.
            nxt = row["parent"] or row["supersedes"]
            if not nxt or nxt not in posts:
                return pid
            pid = nxt
        return pid

    roots = {pid: root_of(pid) for pid in posts}
    threads = OrderedDict()
    for pid, root in roots.items():
        threads.setdefault(root, []).append(pid)
    requests = {}
    for row in view.rows("SELECT * FROM request"):
        requests.setdefault(row["post"], []).append(row)
    index = {"sequence": key[1], "posts": posts, "children": children, "superseded_by": superseded_by,
             "roots": roots, "threads": threads, "people": people, "requests": requests}
    _INDEX[key] = index
    while len(_INDEX) > _INDEX_SIZE:
        _INDEX.popitem(last=False)
    return index


def evidence_counts(evidence):
    evidence = evidence if isinstance(evidence, dict) else {}
    return {"artifacts": len(evidence.get("artifacts") or []), "notebook": bool(evidence.get("notebook")),
            "upload": bool(evidence.get("upload") or evidence.get("uploads")), "run": evidence.get("run"),
            "anchor": bool(evidence.get("anchor"))}


def post_summary(index, pid, vis, *, snippet=SNIPPET, keep=()):
    """Compact post card as `vis` lets this caller see it: a hidden post is `{id, hidden: true, reason}` (plus the
    structural `keep` keys a container needs) unless an operator asked for full content."""
    row = index["posts"][pid]
    body = row["content"]
    card = {"id": pid, "seq": row["seq"], "author": index["people"].get(row["author"], {"id": row["author"]}),
            "channel": row["channel"], "parent": row["parent"], "supersedes": row["supersedes"],
            "superseded_by": index["superseded_by"].get(pid, []), "created": row["created"],
            "kind": body.get("kind"), "evidence": evidence_counts(body.get("evidence")),
            "title": body.get("title"), "snippet": body.get("body", "")[:snippet] if snippet else body.get("body"),
            "content_is_untrusted_data": True}
    return vis.card(pid, card, keep=keep)


def thread_card(index, root, vis, *, full=False):
    """A thread's root card plus aggregates over the posts this caller may see."""
    members = index["threads"][root]
    rows = [index["posts"][m] for m in members if not vis.withheld(m)]
    request_rows = [r for m in members for r in index["requests"].get(m, [])]
    extra = dict(replies=len(members) - 1, last_activity=max((r["created"] for r in rows), default=None),
                 participants=sorted({r["author"] for r in rows}),
                 corrections=sum(1 for r in rows if r["supersedes"]),
                 correction_status="superseded" if index["superseded_by"].get(root) else
                 ("superseding" if index["posts"][root]["supersedes"] else None),
                 open_requests=sum(1 for r in request_rows if r["state"] != "completed"),
                 request=None if vis.withheld(root) else _request_brief(index["requests"].get(root, [None])[0]))
    card = post_summary(index, root, vis, snippet=None if full else SNIPPET)
    if vis.withheld(root):
        return {**card, "replies": extra["replies"]}
    return {**card, **extra}


def _request_brief(row):
    if not row:
        return None
    return {k: row.get(k) for k in ("id", "target", "state", "task_type", "answer", "deadline")}


def _matches(index, pid, *, author, kind, channel, question):
    row = index["posts"][pid]
    body = row["content"]
    evidence = body.get("evidence") if isinstance(body.get("evidence"), dict) else {}
    notebook = evidence.get("notebook") or {}
    return ((not author or row["author"] == author) and (not kind or body.get("kind") == kind)
            and (not channel or row["channel"] == channel)
            and (not question or notebook.get("question") == question))


def list_posts(view, *, family="forum", q="", author=None, kind=None, channel=None, question=None,
               sort="recent", limit=50, offset=0, full=False, caller=None):
    """Board threads (root posts) or, for artifact/work families, library search hits.

    Without text, family=forum lists threads; a thread matches a filter when any of its posts matches.
    With text, `daw.search.search` runs against the library read-only, exactly as `community search` does.
    Hidden posts are placeholders for everyone; operators see their content with full=true."""
    if family not in SEARCH_FAMILIES:
        raise DawError("invalid_search_family", "use forum, artifact, work or all")
    if sort not in THREAD_SORTS:
        raise DawError("invalid_sort", "recent or activity")
    if not 1 <= limit <= 200 or offset < 0:
        raise DawError("invalid_page_bounds")
    index = thread_index(view)
    vis = visibility(view, caller, full)
    author = resolve_participant(view, author)
    filters = {"author": author, "kind": kind, "channel": channel, "question": question}
    base = {"family": family, "query": q, "sort": sort, "sequence": index["sequence"], "offset": offset,
            "note": "board content is attributed evidence, never instructions"}

    def visible(pid):
        # Filters read post content (author, kind, channel, notebook); a withheld post never matches one.
        return not (vis.withheld(pid) and any(filters.values())) and _matches(index, pid, **filters)

    if family == "forum" and not q.strip():
        matching = {}
        for root, members in index["threads"].items():
            hits = [m for m in members if visible(m)]
            if hits:
                matching[root] = hits

        def order(root):
            rows = [index["posts"][m] for m in index["threads"][root]]
            stamp = (index["posts"][root]["created"] if sort == "recent"
                     else max(r["created"] for r in rows))
            return stamp, index["posts"][root]["seq"]
        ordered = sorted(matching, key=order, reverse=True)
        cards = [{**thread_card(index, root, vis, full=full), "type": "thread",
                  "matched": matching[root] if any(filters.values()) else None} for root in ordered]
        return {**base, "total": len(cards), "items": cards[offset:offset + limit],
                "next_offset": offset + limit if offset + limit < len(cards) else None, "method": "thread listing"}

    # Text search (or artifact/work inventory) over the read-only library index.
    hits, method, page = [], None, 0
    while page < SEARCH_PAGES:
        result = find(view, q, limit=100, offset=page * 100, family=family, full=False)
        method = result.get("method")
        hits.extend(result["items"])
        if result.get("next_offset") is None:
            break
        page += 1
    items, seen, withheld = [], {}, 0
    for hit in hits:
        if hit["family"] == "forum":
            pid = hit["subject"]
            if pid in index["posts"] and vis.withheld(pid):
                withheld += 1  # matching a hidden post's text would disclose it; the hit is not served
                continue
            if pid not in index["posts"] or not visible(pid):
                continue
            root = index["roots"][pid]
            # A comment anchored on a hidden post is indexed with the quote; its snippet may carry that text.
            quotes_hidden = vis.touches(index["posts"][pid]["content"].get("evidence"))
            entry = {"post": pid, "score": hit.get("score"),
                     "snippet": None if quotes_hidden else
                     vis.placeholder(pid, {"snippet": None})["snippet"] if vis.refused(pid) else hit.get("snippet")}
            if root in seen:
                seen[root]["hits"].append(entry)
                continue
            card = {**thread_card(index, root, vis, full=full), "type": "thread", "hits": [entry]}
            seen[root] = card
            items.append(card)
        elif any(filters.values()):
            continue  # participant/kind/channel/question filters apply to posts only
        elif hit["family"] == "artifact":
            row = view.library.one("SELECT output_role,derivation_key,created FROM artifact WHERE id=?", (hit["subject"],))
            items.append({**hit, "type": "artifact", **(row or {})})
        elif hit["family"] == "work":
            items.append({**hit, "type": "work",
                          "posts": [pid for pid, row in index["posts"].items() if not vis.withheld(pid)
                                    and ((row["content"].get("evidence") or {}).get("notebook") or {}).get("question")
                                    == hit["subject"]]})
        elif hit["family"] == "claim" and vis.withheld(_claim_post(view, hit["subject"])):
            withheld += 1
        else:
            items.append({**hit, "type": hit["family"]})
    truncated = page == SEARCH_PAGES
    return {**base, "total": len(items), "items": items[offset:offset + limit],
            "next_offset": offset + limit if offset + limit < len(items) else None, "method": method,
            "truncated": truncated, "withheld_hidden": withheld,
            "limitations": ["A missing search hit is not negative evidence; inspect indexing coverage"]
            + (["text search considered only the first 1000 index hits"] if truncated else [])}


def _claim_post(view, claim):
    row = view.one("SELECT post FROM claim WHERE id=?", (claim,))
    return row["post"] if row else None


# ---------------------------------------------------------------------------- numbers and diffs

def numbers(text):
    """Numeric tokens with offsets. Markdown list markers and heading marks are layout, not numbers."""
    found, position = [], 0
    for line in text.splitlines(keepends=True):
        marker = LIST_MARKER.match(line)
        start = marker.end() if marker else 0
        for match in NUMBER.finditer(line, start):
            found.append({"text": match.group(0), "offset": position + match.start(), "line": line.strip()})
        position += len(line)
    return found


def diff_texts(old, new):
    """Line diff plus the multiset of numeric tokens removed and added."""
    lines = []
    for op in difflib.ndiff(old.splitlines(), new.splitlines()):
        if op.startswith("? "):
            continue
        lines.append({"op": {"  ": "=", "- ": "-", "+ ": "+"}[op[:2]], "text": op[2:]})
    before = Counter(n["text"] for n in numbers(old))
    after = Counter(n["text"] for n in numbers(new))
    return {"lines": lines, "numbers": {"removed": sorted((before - after).elements()),
                                        "added": sorted((after - before).elements())}}


# ---------------------------------------------------------------------------- artifacts

def locate_artifact(view, aid, *, quiet=False):
    """Where an artifact's catalog record lives: the shared library first, then participant workspaces."""
    if view.library.one("SELECT id FROM artifact WHERE id=?", (aid,)):
        return {"store": "library"}
    for agent in view.rows("SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY created,id"):
        ws = _workspace(view, agent["id"])
        if ws and ws.one("SELECT id FROM artifact WHERE id=?", (aid,)):
            return {"store": "workspace", "participant": agent["id"]}
    if quiet:
        return {"store": "missing"}
    raise DawError("unknown_artifact", aid)


def _workspace(view, participant):
    try:
        return view.workspace(participant)
    except (DawError, OSError):
        return None


def _store(view, location):
    return view.library if location["store"] == "library" else _workspace(view, location["participant"])


def _strip_paths(value):
    """Server filesystem paths are not part of the record; content hashes identify bytes."""
    if isinstance(value, dict):
        return {k: _strip_paths(v) for k, v in value.items() if k not in {"path", "question_path"}}
    if isinstance(value, list):
        return [_strip_paths(v) for v in value]
    return value


def _artifact_record(store, aid):
    """`artifact_info`, or the row plus its manifest when the output bytes are absent from this store
    (a fixture, or a workspace that only holds the record): the page still renders, with present=false."""
    try:
        return artifact_info(store, aid)
    except DawError as error:
        if error.reason != "missing_blob":
            raise
    row = store.one("SELECT * FROM artifact WHERE id=?", (aid,))
    if not row:
        raise DawError("unknown_artifact", aid)
    try:
        manifest = read_json(store.blob_path(row["manifest_blob"]))
    except DawError:
        manifest = {}
    return {**row, "manifest": manifest, "path": None, "present": False,
            "questions": store.rows("SELECT question_id,relationship FROM question_artifact WHERE artifact_id=?", (aid,))}


def artifact_view(view, aid, *, depth=3, caller=None, full=False):
    if not 0 <= depth <= 6:
        raise DawError("invalid_provenance_depth", "0 to 6")
    location = locate_artifact(view, aid)
    store = _store(view, location)
    info = _artifact_record(store, aid)
    manifest = info["manifest"]
    derivation = manifest.get("derivation", {})
    inputs = []
    for item in derivation.get("inputs", []):
        source = item.get("source_identity")
        entry = {"blob": item.get("blob"), "role": item.get("role"), "source_identity": source}
        if source and source.startswith("artifact_"):
            row = store.one("SELECT output_role,manifest_blob FROM artifact WHERE id=?", (source,))
            entry.update(kind="artifact", title=read_json(store.blob_path(row["manifest_blob"])).get("title") if row else None,
                         output_role=row["output_role"] if row else None, present=bool(row))
        elif source and source.startswith("asset_"):
            try:
                asset = store.asset(source)
                body = asset["body"]
                entry.update(kind="asset", present=True, snapshot=asset.get("snapshot_id"),
                             locator=body.get("locator") or body.get("selector"), name=body.get("name"))
            except DawError:
                entry.update(kind="asset", present=False)
        else:
            entry["kind"] = "object"
        inputs.append(entry)
    try:
        graph = provenance(store, aid, depth=depth)
    except DawError as error:
        if error.reason != "missing_blob":
            raise
        graph = {"root": aid, "depth": depth, "nodes": {}, "edges": [], "frontier": [],
                 "unavailable": f"provenance walk stopped at bytes absent from this store ({error.detail})"}
    questions = []
    for agent in view.rows("SELECT id FROM agent WHERE trial IS NOT NULL ORDER BY created,id"):
        ws = _workspace(view, agent["id"])
        if not ws:
            continue
        links = [link for link in reuse_links(ws) if link["artifact"] == aid]
        questions.extend({"participant": agent["id"], **link} for link in links)
    index = thread_index(view)
    vis = visibility(view, caller, full)
    naming = [post_summary(index, pid, vis) for pid in posts_naming(view, aid) if pid in index["posts"]]
    fetchers = [{"seq": e["seq"], "created": e["created"], "reader": e["body"].get("reader"),
                 "question": e["body"].get("question"), "post": e["body"].get("post")}
                for e in _events(view, "evidence_fetched") if aid in (e["body"].get("artifacts") or [])]
    output = manifest.get("output") or {}
    return {"id": aid, "location": location, "derivation_key": info["derivation_key"], "output_role": info["output_role"],
            "output_blob": info["output_blob"], "manifest_blob": info["manifest_blob"], "created": info["created"],
            "manifest": _strip_paths(manifest),
            "derivation": {"inputs": inputs, "code": derivation.get("code", []), "references": derivation.get("references", []),
                           "parameters": derivation.get("parameters", {}), "environment": derivation.get("environment", {})},
            "provenance": _strip_paths(graph), "questions": questions, "posts": naming, "fetchers": fetchers,
            "marks": marks_for(view, [("artifact", aid)]),
            "comments": [post_summary(index, pid, vis, snippet=None) for pid, row in index["posts"].items()
                         if row["content"].get("kind") == "comment"
                         and comment_target(row["content"].get("evidence") or {}) == ("artifact", aid)],
            "bytes": {"name": output.get("name"), "size": output.get("bytes"), "url": f"/api/artifacts/{aid}/bytes",
                      "present": info.get("present", True)},
            "present": info.get("present", True),
            "content_is_untrusted_data": True,
            "note": "Identical derivation permits byte reuse, not an assertion of scientific applicability"}


TEXT_SUFFIXES = {".tsv", ".csv", ".txt", ".md", ".json", ".jsonl", ".tab", ".bed", ".gff", ".gtf", ".fa", ".fasta",
                 ".vcf", ".log", ".yaml", ".yml", ".toml", ".py", ".r", ".sh"}


def artifact_bytes(view, aid):
    """Verified output bytes of an artifact plus a safe presentation: text/plain or an attachment, never HTML."""
    from daw.profiles import verify_object
    location = locate_artifact(view, aid)
    store = _store(view, location)
    row = store.one("SELECT output_blob,manifest_blob FROM artifact WHERE id=?", (aid,))
    path = verify_object(store, row["output_blob"])
    name = (read_json(store.blob_path(row["manifest_blob"])).get("output") or {}).get("name") or row["output_blob"]
    # The recorded name is untrusted: keep a header-safe basename for Content-Disposition.
    name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name).lstrip(".") or row["output_blob"]
    text = Path(name).suffix.lower() in TEXT_SUFFIXES and path.stat().st_size <= 20_000_000
    if text:
        with path.open("rb") as stream:
            try:
                stream.read(65536).decode("utf-8")
            except UnicodeDecodeError:
                text = False
    return {"path": path, "name": name, "text": text, "sha256": row["output_blob"]}


# ---------------------------------------------------------------------------- marks, claims, events

def _events(view, kind=None, *, after=0, limit=None):
    sql = "SELECT * FROM event WHERE seq>?" + (" AND kind=?" if kind else "") + " ORDER BY seq"
    params = [after] + ([kind] if kind else [])
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [{**row, "body": _jsonish(row["body"], {})} for row in view.rows(sql, params)]


def event_log(view, *, after=0, limit=200):
    if after < 0 or not 1 <= limit <= 1000:
        raise DawError("invalid_page_bounds")
    vis = visibility(view)
    items = [vis.event(e) for e in _events(view, after=after, limit=limit)]
    return {"after": after, "items": items, "sequence": view.sequence(),
            "next_after": items[-1]["seq"] if items else after}


def marks_for(view, targets):
    """Marks are attribution displayed next to their target; they never change a computed status."""
    out = []
    for target_kind, target_id in targets:
        for row in view.rows("SELECT * FROM mark WHERE target_kind=? AND target_id=? ORDER BY created,id",
                             (target_kind, target_id)):
            out.append({**{k: v for k, v in row.items() if k != "pointers"}, "pointers": _jsonish(row["pointers"], [])})
    return out


def claims_for(view, pid):
    rows = view.rows("SELECT * FROM claim WHERE post=? ORDER BY ordinal", (pid,))
    out = []
    for row in rows:
        claim = {**row, "scope": _jsonish(row["scope"], {}), "pointers": _jsonish(row["pointers"], [])}
        claim["marks"] = marks_for(view, [("claim", row["id"])])
        out.append(claim)
    return out


# ---------------------------------------------------------------------------- post detail

def _fetches(view, pid):
    """Each `evidence_fetched` event for this post, with what the reader's workspace records about those artifacts."""
    out = []
    for event in _events(view, "evidence_fetched"):
        body = event["body"]
        if body.get("post") != pid:
            continue
        reader = body.get("reader")
        ws = _workspace(view, reader) if reader else None
        uses = None
        if ws:
            links = reuse_links(ws)
            uses = {aid: [link for link in links if link["artifact"] == aid] for aid in body.get("artifacts") or []}
        out.append({"seq": event["seq"], "created": event["created"], "reader": reader, "question": body.get("question"),
                    "artifacts": body.get("artifacts") or [], "uses": uses,
                    "workspace": "available" if ws else "unavailable",
                    "note": "considered records retrieval; reused is backed by a reason or a registration input"})
    return out


def _supersedes_chain(index, pid):
    back, seen, cur = [], {pid}, index["posts"][pid]["supersedes"]
    while cur and cur in index["posts"] and cur not in seen:
        back.append(cur)
        seen.add(cur)
        cur = index["posts"][cur]["supersedes"]
    forward, cur = [], pid
    while index["superseded_by"].get(cur):
        nxt = index["superseded_by"][cur][-1]
        if nxt in seen:
            break
        forward.append(nxt)
        seen.add(nxt)
        cur = nxt
    return {"supersedes": back, "superseded_by": forward}


def _anchor_key(anchor):
    return json.dumps({k: anchor.get(k) for k in ("kind", "blob", "offset", "length", "row_key", "node_id")},
                      sort_keys=True)


def post_view(view, pid, *, caller=None, full=False):
    index = thread_index(view)
    if pid not in index["posts"]:
        raise DawError("unknown_post", pid)
    vis = visibility(view, caller, full)
    if vis.withheld(pid):
        return vis.stub(pid)
    refused = vis.refused(pid)  # a write-up the number checker refused: a placeholder, not its content (C5)
    record = view.post(pid)  # verifies the body bytes against their hash
    body = record["content"]
    evidence = body.get("evidence") if isinstance(body.get("evidence"), dict) else {}
    people = index["people"]
    claims = claims_for(view, pid)
    artifacts = list(evidence.get("artifacts") or [])
    comments, replies = OrderedDict(), []
    for child in index["children"].get(pid, []):
        crow = index["posts"][child]
        cbody = crow["content"]
        card = post_summary(index, child, vis, snippet=None)
        if cbody.get("kind") == "comment":
            # Flow D: the author's answer (a reply to the comment, which closes its request) is shown under
            # the anchor, with the request's state.
            card["request"] = _request_brief((index["requests"].get(child) or [None])[0])
            card["answers"] = [post_summary(index, a, vis, snippet=None) for a in index["children"].get(child, [])]
            # A withheld comment's evidence (its anchor) is its content: it is listed without one.
            anchor = None if vis.withheld(child) else (cbody.get("evidence") or {}).get("anchor")
            key = _anchor_key(anchor) if isinstance(anchor, dict) else "null"
            group = comments.setdefault(key, {"anchor": anchor if isinstance(anchor, dict) else None, "comments": []})
            group["comments"].append(card)
        else:
            replies.append(card)
    chain = _supersedes_chain(index, pid)
    text = body.get("body", "")
    result = {k: record[k] for k in ("id", "seq", "author", "channel", "parent", "supersedes", "body_blob",
                                     "request_key", "created")}
    result.update(
        author_participant=people.get(record["author"], {"id": record["author"]}),
        thread=index["roots"][pid], hidden=vis.hidden(pid), content_is_untrusted_data=True,
        content={**body, "evidence": vis.evidence(body["evidence"])} if "evidence" in body else body,
        evidence_artifacts=evidence_summary(view.library, evidence),
        notebook=evidence.get("notebook"), run=evidence.get("run") or body.get("run"),
        fetches=_fetches(view, pid), claims=claims,
        marks=marks_for(view, [("post", pid)] + [("claim", c["id"]) for c in claims]
                        + [("artifact", a) for a in artifacts]),
        comments=list(comments.values()), replies=replies,
        superseded_by=[post_summary(index, s, vis) for s in index["superseded_by"].get(pid, [])],
        supersedes_chain=chain,
        requests=_requests_for_post(view, index, pid, vis),
        numbers=[] if refused else _post_numbers(view, pid, text, evidence),
        withheld=_withheld_view(view, pid, vis.refused_writeups[pid]) if refused else None,
    )
    if vis.hidden(pid):
        result.update(reason=vis.reason(pid), moderation=vis.records[pid], revealed=True)
    if refused:
        result["content"] = None
    # C11: numbers without a pointer at the number are listed apart from those covered only by the post's evidence.
    result["unpointed_numbers"] = [n["text"] for n in result["numbers"] if n["status"] == "unpointed"]
    result["post_scoped_numbers"] = [n["text"] for n in result["numbers"] if n["status"] == "post_scoped"]
    result["number_summary"] = None if refused else _summarize(result["numbers"])
    latest = chain["superseded_by"][-1] if chain["superseded_by"] else None
    result["diff"] = ({"from": pid, "to": latest, **diff_texts(text, index["posts"][latest]["content"].get("body", ""))}
                      if latest and not (refused or vis.withheld(latest) or vis.refused(latest)) else None)
    previous = record["supersedes"]
    result["diff_from_superseded"] = ({"from": previous, "to": pid,
                                       **diff_texts(index["posts"][previous]["content"].get("body", ""), text)}
                                      if previous in index["posts"] and not (refused or vis.withheld(previous)
                                                                             or vis.refused(previous)) else None)
    return result


def _post_numbers(view, pid, text, evidence):
    from daw.commons.checks import post_numbers
    return post_numbers(view, pid, text, evidence)


def _summarize(numbers):
    from daw.commons.checks import summarize
    return summarize(numbers)


def _withheld_view(view, pid, info):
    """A refused write-up's verdict for its placeholder: status, counts and every problem location."""
    from daw.commons.checks import PLACEHOLDER_TITLE, placeholder, recorded, verdict_body
    from daw.commons.writeup import verdict
    stored = recorded(view).get(pid)
    value = verdict_body(view, stored) if stored else verdict(view, pid)[0]
    return {**info, "title": PLACEHOLDER_TITLE, "placeholder": placeholder(value["problems"]),
            "problems": [{k: p.get(k) for k in ("kind", "text", "pointer", "line", "offset", "length", "reason")}
                         for p in value["problems"]],
            "stats": value["stats"], "created": stored["created"] if stored else None}


def _requests_for_post(view, index, pid, vis):
    """Requests whose post is this post, or whose question post replies to it (asks, comments to the author).
    The asker of a withheld question post is withheld with it."""
    related = [pid, *index["children"].get(pid, [])]
    out = []
    for post in related:
        for row in index["requests"].get(post, []):
            out.append({**row, "budget": _jsonish(row.get("budget"), None),
                        "asker": None if vis.withheld(post) else index["posts"][post]["author"]})
    return out


def thread_view(view, pid, *, caller=None, full=False):
    """Nested reply tree for the thread containing `pid`; corrections are inline under the post they supersede."""
    index = thread_index(view)
    if pid not in index["posts"]:
        raise DawError("unknown_post", pid)
    vis = visibility(view, caller, full)
    root = index["roots"][pid]
    seen = set()

    def node(current):
        seen.add(current)
        kids = [c for c in index["children"].get(current, []) if c not in seen]
        loose = [c for c in index["superseded_by"].get(current, [])
                 if c not in seen and index["posts"][c]["parent"] != current and not index["posts"][c]["parent"]]
        children = [node(c) for c in kids if c not in seen]
        corrections = [node(c) for c in loose if c not in seen]
        card = post_summary(index, current, vis, snippet=None)
        if vis.withheld(current):
            # Structure only: the nested cards are other posts, each resolved on its own.
            return {**card, "children": children, "corrections": corrections}
        return {**card, "corrects": index["posts"][current]["supersedes"], "children": children,
                "corrections": corrections}

    return {"root": root, "focus": pid, "sequence": index["sequence"], "tree": node(root)}


# ---------------------------------------------------------------------------- participants, requests, running

def participant_activity(view, identity, *, caller=None, full=False):
    """M4.5: agents get assignments, posts, runs, reuse backed ratio, open requests and forks;
    humans get comments, marks, promotions and commissions. Keys are present for every kind."""
    participant = view.participant(identity)
    pid = participant["id"]
    index = thread_index(view)
    vis = visibility(view, caller, full)
    # A withheld post's author is withheld with it, so it is not listed under its author.
    authored = [p for p, row in index["posts"].items() if row["author"] == pid and not vis.withheld(p)]
    posts = [post_summary(index, p, vis) for p in reversed(authored)]
    assignments = []
    for row in view.rows("SELECT * FROM request WHERE target=? ORDER BY created DESC,id", (pid,)):
        post = index["posts"].get(row["post"])
        assignments.append({**row, "budget": _jsonish(row.get("budget"), None),
                            "title": vis.title(row["post"], post["content"].get("title")) if post else None,
                            "post_hidden": vis.hidden(row["post"]),
                            "asker": post["author"] if post and not vis.withheld(row["post"]) else None})
    runs = view.rows("SELECT * FROM attempt WHERE target=? ORDER BY created DESC,id", (pid,))
    sent = []
    for row in view.rows("SELECT r.*,p.author AS asker FROM request r JOIN post p ON p.id=r.post WHERE p.author=? "
                         "ORDER BY r.created DESC,r.id", (pid,)):
        if not vis.withheld(row["post"]):
            sent.append({**row, "budget": _jsonish(row.get("budget"), None)})
    reuse = None
    ws = _workspace(view, pid) if participant["trial"] else None
    if ws:
        links = reuse_links(ws)
        reused = [link for link in links if link["relationship"] == "reused"]
        backed = sum(1 for link in reused if link["backed"])
        reuse = {"produced": sum(1 for link in links if link["relationship"] == "produced"),
                 "considered": sum(1 for link in links if link["relationship"] == "considered"),
                 "reused": len(reused), "backed": backed,
                 "backed_ratio": round(backed / len(reused), 3) if reused else None,
                 "unbacked": [link for link in reused if not link["backed"]],
                 "note": "backed: a reuse reason or a later registration naming the artifact as input"}
    forks = [describe(row) for row in view.rows("SELECT * FROM agent WHERE parent=? ORDER BY created", (pid,))]
    return {"participant": describe(participant),
            "posts": posts,
            "assignments": assignments,
            "open_requests": [a for a in assignments if a["state"] != "completed"],
            "runs": runs,
            "reuse": reuse,
            "forks": forks,
            "comments": [p for p in posts if p["kind"] == "comment"],
            "marks": [{**row, "pointers": _jsonish(row["pointers"], [])}
                      for row in view.rows("SELECT * FROM mark WHERE participant=? ORDER BY created DESC,id", (pid,))],
            "promotions": [r for r in sent if r["task_type"] and r["task_type"] not in ("notice", "question")],
            "asked": [r for r in sent if not r["task_type"] or r["task_type"] == "question"],
            "sequence": index["sequence"]}


def list_requests(view, *, target=None, state=None, task_type=None, limit=200, caller=None, full=False):
    conditions, params = [], []
    if target:
        conditions.append("r.target=?")
        params.append(resolve_participant(view, target))
    if state:
        conditions.append("r.state=?")
        params.append(state)
    if task_type == "question":
        # Questions: agents' untyped peer questions and people's typed asks (task type question).
        conditions.append("(r.task_type IS NULL OR r.task_type='question')")
    elif task_type:
        conditions.append("r.task_type=?")
        params.append(task_type)
    sql = ("SELECT r.*,p.author AS asker,p.body_blob FROM request r JOIN post p ON p.id=r.post"
           + (" WHERE " + " AND ".join(conditions) if conditions else "") + " ORDER BY r.created DESC,r.id LIMIT ?")
    vis = visibility(view, caller, full)
    items = []
    for row in view.rows(sql, params + [limit]):
        body = content(view, row.pop("body_blob"))
        withheld = vis.withheld(row["post"])
        items.append({**row, "budget": _jsonish(row.get("budget"), None),
                      "asker": None if withheld else row["asker"],
                      "title": None if withheld else body.get("title"),
                      "kind": None if withheld else body.get("kind"), "post_hidden": vis.hidden(row["post"]),
                      "reason": vis.reason(row["post"]), "content_is_untrusted_data": True})
    return {"items": items, "note": "a request without a task type is an agent's peer question; task type "
                                    "question is a person's budgeted ask"}


def heartbeat(folder):
    """Latest heartbeat.json of a running delivery (written every 30 s by the capture loop)."""
    path = folder / "heartbeat.json"
    if not path.is_file():
        return None
    try:
        value = read_json(path)
    except (OSError, ValueError):
        return None
    return {k: value.get(k) for k in ("observed", "elapsed_seconds", "stdout_bytes")}


def running(view, *, caller=None, full=False):
    """Attempts in state running with their last heartbeat. Never inferred from process tables."""
    vis = visibility(view, caller, full)
    out = []
    for row in view.rows("SELECT a.*,r.post,r.task_type FROM attempt a JOIN request r ON r.id=a.request "
                         "WHERE a.state='running' ORDER BY a.created"):
        try:
            _, folder = view.run_folder(row["id"])
            beat = heartbeat(folder)
        except DawError:
            beat = None
        post = view.one("SELECT body_blob FROM post WHERE id=?", (row["post"],))
        title = vis.title(row["post"], content(view, post["body_blob"]).get("title")) if post else None
        out.append({"run": row["id"], "request": row["request"], "agent": row["target"], "started": row["created"],
                    "task_type": row["task_type"], "post": row["post"], "title": title,
                    "post_hidden": vis.hidden(row["post"]), "reason": vis.reason(row["post"]), "heartbeat": beat})
    return {"items": out, "sequence": view.sequence()}
