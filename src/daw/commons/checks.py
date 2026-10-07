"""Checker verdicts as records (C5) and number reports for every post (C11, V2).

One checker (`daw.commons.writeup.check`) serves every rendering of a write-up:

- **At delivery.** After a `writing` or `digest` task is delivered, the runtime's post-delivery hook
  (`daw.commons.studio.after_delivery` -> `after_delivery` here) checks the answer and every post published
  during the run, stores the verdict JSON as a library blob and appends an immutable `writeup_check` board
  event: post, request, status (`rendered` | `refused`), rules version, verdict blob, counts, every problem
  and every number's location, scope and status. A refused write-up still completes its request.
  Recording is idempotent: an unchanged verdict (same blob) appends nothing; a changed one (an operator
  re-check after the ledger changed) appends a new event and the latest is the record.
- **At read.** `/post/:id`, thread and listing cards, search snippets, digest skeletons, Studio and export
  read the record (`recorded`). A refused write-up is served as a placeholder everywhere (its bytes stay
  in the library). A write-up post without a record (a hook that failed) is checked at read time by the
  same function and labelled `computed`. `writeup.regeneration` is still evaluated at render, so later
  withdrawals flag a write-up without rewriting its verdict.

Every other post gets a number report (`post_numbers`) from the same parser and value-in-record check:
a number covered by a pointer at the number is `verified` or `unverified` with scope `cell`, `claim` or
`line`; a number without one is `post_scoped` when the post names evidence (its evidence list, artifact
identifiers elsewhere in the text, its ledger claims), shown as "this post's evidence" rather than as a
link from the number (C11), and `unpointed` otherwise. Nothing here writes except `record`.
"""
import json
from collections import OrderedDict
from urllib.parse import quote

from daw.commons import federation, views, writeup
from daw.commons.archive import Archive
from daw.util import DawError

WRITEUP_TYPES = ("writing", "digest")
EVENT = "writeup_check"
PLACEHOLDER_TITLE = "Write-up withheld: refused by the number checker"
NUMBER_LEVEL = ("cell", "claim", "line")
_CACHE: "OrderedDict[tuple, object]" = OrderedDict()


def _cached(key, compute, size=64):
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    value = compute()
    _CACHE[key] = value
    while len(_CACHE) > size:
        _CACHE.popitem(last=False)
    return value


# ---------------------------------------------------------------------------- records

def recorded(view):
    """{post: latest writeup_check event body (+ seq, created)}. Cached per board sequence."""
    def compute():
        latest = {}
        for row in view.rows("SELECT seq,body,created FROM event WHERE kind=? ORDER BY seq", (EVENT,)):
            body = json.loads(row["body"])
            latest[body["post"]] = {**body, "seq": row["seq"], "created": row["created"]}
        return latest
    return _cached(("recorded", str(view.root), view.sequence()), compute)


def verdict_body(view, stored):
    """The stored verdict JSON (library blob, verified against its hash)."""
    return view.library.json_blob(stored["verdict_blob"], verify=True)


def writeup_posts(view):
    """{post: request row} for every answer of, and post published during, a writing or digest request."""
    def compute():
        requests = {r["id"]: r for r in view.rows("SELECT * FROM request WHERE task_type IN (?,?)", WRITEUP_TYPES)}
        out = {r["answer"]: r for r in requests.values() if r["answer"]}
        for row in view.rows("SELECT body FROM event WHERE kind='task_outcome' ORDER BY seq"):
            body = json.loads(row["body"])
            if body.get("request") in requests:
                for post in (body.get("criteria") or {}).get("posts_published") or []:
                    out.setdefault(post, requests[body["request"]])
        return out
    return _cached(("writeups", str(view.root), view.sequence()), compute)


def _compact(value, blob, actor):
    return {"post": value["post"], "request": value["request"], "task_type": value["task_type"],
            "status": value["status"], "rules": value["rules"], "verdict_blob": blob, "body_blob": value["body_blob"],
            "stats": value["stats"], "actor": actor,
            "problems": [{k: p.get(k) for k in ("kind", "text", "pointer", "offset", "length", "line") if p.get(k) is not None}
                         for p in value["problems"]],
            "numbers": [{k: n[k] for k in ("text", "offset", "length", "line", "scope", "status")}
                        | {"pointers": [p["id"] + (f"#{p['locator']}" if p.get("locator") else "") for p in n["pointers"]
                                        if p.get("kind") in writeup.COVERING]}
                        for n in value["numbers"]]}


def record(board, post_id, request=None, *, actor="runtime"):
    """Check a write-up and store the verdict (library blob + `writeup_check` event). Idempotent per verdict."""
    with Archive(board.root) as view:
        if request is None:
            request = writeup.writing_request(view, post_id)
        value, _, _ = writeup.verdict(view, post_id, request=request)
        latest = recorded(view).get(post_id)
    with board.writer(), board.library.writer():
        blob = board.library.put_json(value)
        created = not latest or latest["verdict_blob"] != blob
        if created:
            with board.db:
                board.event(EVENT, _compact(value, blob, actor))
    return {"post": post_id, "status": value["status"], "verdict_blob": blob, "problems": len(value["problems"]),
            "stats": value["stats"], "created": created}


def outputs_of(board, request):
    """The answer and every post published during the delivery (from the runtime's latest task_outcome)."""
    published = []
    for row in board.rows("SELECT body FROM event WHERE kind='task_outcome' ORDER BY seq"):
        body = json.loads(row["body"])
        if body.get("request") == request["id"]:
            published = (body.get("criteria") or {}).get("posts_published") or []
    return list(dict.fromkeys(([request["answer"]] if request["answer"] else []) + published))


def after_delivery(board, request):
    """Post-delivery hook for writing and digest requests: record a verdict for every output post."""
    if request["task_type"] not in WRITEUP_TYPES:
        return None
    return [record(board, post, request) for post in outputs_of(board, request)]


# ---------------------------------------------------------------------------- readers

def verdicts(view):
    """{post: {status, source, problems, seq?}} for every write-up post: the record, else checked now."""
    def compute():
        stored = recorded(view)
        out = {pid: {"status": s["status"], "source": "recorded", "problems": len(s.get("problems") or []),
                     "seq": s["seq"], "verdict_blob": s["verdict_blob"]} for pid, s in stored.items()}
        for pid, request in writeup_posts(view).items():
            if pid in out:
                continue
            try:
                value, _, _ = writeup.verdict(view, pid, request=request)
            except DawError:
                continue
            out[pid] = {"status": value["status"], "source": "computed", "problems": len(value["problems"])}
        return out
    from daw.commons.evidence_map import fingerprint
    return _cached(("verdicts", str(view.root), view.sequence(), fingerprint(view)), compute)


def withheld(view):
    """{post: verdict summary} for refused write-ups: every surface shows a placeholder instead of their content."""
    return {pid: v for pid, v in verdicts(view).items() if v["status"] == "refused"}


def placeholder(problems):
    count = len(problems or [])
    kinds = sorted({p.get("kind") for p in problems or [] if p.get("kind")})
    return (f"This write-up was refused by the number checker ({count} problem{'s' if count != 1 else ''}: "
            f"{', '.join(kinds) or 'see the verdict'}). It is withheld on every surface; its bytes are kept and the "
            "verdict lists every location. Commission a corrected write-up.")


def snippet(info):
    """The placeholder text shown in cards and search results for a withheld write-up."""
    return f"[{PLACEHOLDER_TITLE.lower()}; {info.get('problems', 0)} problem(s)]"


# ---------------------------------------------------------------------------- number reports

def post_evidence(view, pid, text, evidence):
    """What a post names as its evidence: evidence artifacts, artifact identifiers in its text, its claims."""
    evidence = evidence if isinstance(evidence, dict) else {}
    local_text = federation.FOREIGN.sub("", text or "")  # snapshot:<id>/artifact_… names a foreign record (V7)
    artifacts = list(dict.fromkeys(views.ARTIFACT_ID.findall(local_text)
                                   + [a for a in evidence.get("artifacts") or [] if isinstance(a, str)]))
    claims = [r["id"] for r in view.rows("SELECT id FROM claim WHERE post=? ORDER BY ordinal", (pid,))]
    return [{"kind": "artifact", "id": a, "artifact": a, "location": views.locate_artifact(view, a, quiet=True),
             "post_evidence": True} for a in artifacts] + [{"kind": "claim", "id": c, "post_evidence": True}
                                                           for c in claims]


def _decorate(view, pointer, located):
    if pointer.get("kind") == "artifact" and federation.split(pointer.get("id")):
        snapshot, record = federation.split(pointer["id"])  # V7: a record of an imported snapshot
        return {**pointer, "artifact": pointer["id"], "foreign": True, "snapshot": snapshot,
                "location": {"store": "federation", "snapshot": snapshot},
                "route": f"/directory/{snapshot}#{record}"}
    if pointer.get("kind") == "artifact":
        aid = pointer["id"]
        if aid not in located:
            located[aid] = views.locate_artifact(view, aid, quiet=True)
        pointer = {**pointer, "artifact": aid, "location": located[aid]}
        locator = pointer.get("locator")
        found = pointer.get("found") or {}
        if not locator and pointer.get("at") == "text" and found.get("line"):
            locator = f"line={found['line']}"  # where the checker found the value: open the page there
        pointer["route"] = f"/artifact/{aid}" + (f"?locator={quote(locator, safe='')}" if locator else "")
    return pointer


def post_numbers(view, pid, text, evidence):
    """Every number of a post with scope (cell | claim | line | post | none), status (verified | unverified |
    post_scoped | unpointed) and pointers. Write-ups report their verdict's numbers (recorded or computed)."""
    def compute():
        located = {}
        stored = recorded(view).get(pid)
        if stored or pid in writeup_posts(view):
            if stored:
                records = verdict_body(view, stored)["numbers"]
            else:
                records = writeup.verdict(view, pid)[0]["numbers"]
            return [{**r, "pointers": [_decorate(view, p, located) for p in r["pointers"]], "writeup": True}
                    for r in records]
        blocks = writeup.parse(text or "")
        writeup.verify_numbers(view, blocks, {})
        records = writeup.number_records(text or "", blocks)
        named = post_evidence(view, pid, text, evidence)
        out = []
        for r in records:
            pointers = [_decorate(view, p, located) for p in r["pointers"] if p.get("kind") in writeup.COVERING]
            if r["scope"] == "none" and named:
                r = {**r, "scope": "post", "status": "post_scoped",
                     "reason": "the post names evidence, but no pointer sits at this number"}
                pointers = named
            out.append({**r, "pointers": pointers})
        return out
    from daw.commons.evidence_map import fingerprint
    return _cached(("numbers", str(view.root), view.sequence(), fingerprint(view), pid), compute, size=512)


def summarize(numbers):
    """Counts by scope and status, and the number-level share (cell, claim or line pointers) of all numbers."""
    total = len(numbers)
    scopes = {s: sum(1 for n in numbers if n["scope"] == s) for s in ("cell", "claim", "line", "post", "none")}
    statuses = {s: sum(1 for n in numbers if n["status"] == s)
                for s in ("verified", "unverified", "post_scoped", "unpointed")}
    level = sum(scopes[s] for s in NUMBER_LEVEL)
    return {"numbers": total, "scopes": scopes, "statuses": statuses, "number_level": level,
            "number_level_share": round(level / total, 4) if total else None,
            "verified_share": round(statuses["verified"] / total, 4) if total else None,
            "cell_verified": sum(1 for n in numbers if n["status"] == "verified" and n["scope"] == "cell")}


def finals(view):
    """{answer post: {request, requester, requester_kind}} for research deliveries: answers of requests typed
    `research`, or untyped requests that are not answer notifications or platform notices."""
    def compute():
        people = {r["id"]: r["kind"] for r in view.rows("SELECT id,kind FROM agent")}
        out = {}
        for row in view.rows("SELECT r.id,r.answer,r.task_type,p.author,p.body_blob FROM request r "
                             "JOIN post p ON p.id=r.post WHERE r.answer IS NOT NULL ORDER BY r.created,r.id"):
            if row["task_type"] not in (None, "research"):
                continue
            kind = views.content(view, row["body_blob"]).get("kind")
            if row["task_type"] is None and kind in ("answer_notification", "notice"):
                continue
            out[row["answer"]] = {"request": row["id"], "requester": row["author"],
                                  "requester_kind": people.get(row["author"])}
        return out
    return _cached(("finals", str(view.root), view.sequence()), compute)


def number_summary(view, pid):
    """summarize(post_numbers) for one post; hidden posts and withheld write-ups count nothing (not zero)."""
    row = views.thread_index(view)["posts"].get(pid)
    if not row:
        raise DawError("unknown_post", pid)
    content = row["content"]
    return summarize(post_numbers(view, pid, content.get("body") or "", content.get("evidence")))


def verified_claim_pointers(view):
    """{claim: number of verified number->claim pointers} across the latest recorded verdict of every write-up."""
    def compute():
        counts = {}
        for stored in recorded(view).values():
            if stored.get("status") != "rendered":
                continue
            for number in verdict_body(view, stored)["numbers"]:
                for pointer in number["pointers"]:
                    if pointer.get("kind") == "claim" and pointer.get("result") == "verified":
                        counts[pointer["id"]] = counts.get(pointer["id"], 0) + 1
        return counts
    return _cached(("claims", str(view.root), view.sequence()), compute)


# ---------------------------------------------------------------------------- audit (V2 Milestone B)

def _named_value(view, number, artifacts, outputs):
    """Audit only: does a post-scoped number's value occur in one of the artifacts the post names?
    (Never displayed as a pointer; it measures how many numbers an author could have pointed.)"""
    from daw.commons import locators
    value = locators.parse_number(number["text"])
    absent = 0
    for aid in artifacts:
        result = locators.verify_artifact(view, aid, None, value, outputs)
        if result["result"] == "verified":
            return "found", absent
        if "absent" in (result.get("reason") or ""):
            absent += 1
    return ("bytes_absent" if absent and absent == len(artifacts) else "not_found"), absent


def audit(view, *, posts=None):
    """Per final: numbers by scope and status, the share resolvable to a cell, and (audit only) how many
    post-scoped numbers occur in the post's named artifacts. Ids and counts only; no prose."""
    index = views.thread_index(view)
    hidden = views.hidden_posts(view)
    chosen = finals(view) if posts is None else {p: {} for p in posts}
    rows, outputs = [], {}
    for pid, info in chosen.items():
        if pid not in index["posts"] or pid in hidden:
            continue
        content = index["posts"][pid]["content"]
        numbers = post_numbers(view, pid, content.get("body") or "", content.get("evidence"))
        summary = summarize(numbers)
        artifacts = [p["id"] for p in post_evidence(view, pid, content.get("body"), content.get("evidence"))
                     if p["kind"] == "artifact"]
        named = {"found": 0, "not_found": 0, "bytes_absent": 0}
        for number in numbers:
            if number["status"] == "post_scoped":
                outcome, _ = _named_value(view, number, artifacts, outputs)
                named[outcome] += 1
        rows.append({"post": pid, "request": info.get("request"), "requester_kind": info.get("requester_kind"),
                     **summary, "post_scoped_value_in_named_artifact": named})

    def total(group):
        numbers = sum(r["numbers"] for r in group)
        keys = ("cell", "claim", "line", "post", "none")
        scopes = {k: sum(r["scopes"][k] for r in group) for k in keys}
        statuses = {k: sum(r["statuses"][k] for r in group) for k in ("verified", "unverified", "post_scoped", "unpointed")}
        named = {k: sum(r["post_scoped_value_in_named_artifact"][k] for r in group)
                 for k in ("found", "not_found", "bytes_absent")}
        def share(count):
            return round(count / numbers, 4) if numbers else None
        return {"finals": len(group), "finals_with_numbers": sum(1 for r in group if r["numbers"]),
                "numbers": numbers, "scopes": scopes, "statuses": statuses,
                "shares": {"resolvable_to_cell": share(sum(r["cell_verified"] for r in group)),
                           "number_level_pointer": share(sum(r["number_level"] for r in group)),
                           "verified": share(statuses["verified"]), "unverified": share(statuses["unverified"]),
                           "post_scoped": share(statuses["post_scoped"]), "unpointed": share(statuses["unpointed"])},
                "finals_with_a_cell_resolvable_number": sum(1 for r in group if r["cell_verified"]),
                "post_scoped_value_in_named_artifact": named}

    groups = {"all": rows, "assignment": [r for r in rows if r["requester_kind"] in ("operator", "human")],
              "peer": [r for r in rows if r["requester_kind"] == "agent"]}
    return {"format": "colloquy.number-audit/1", "rules": writeup.RULES_VERSION, "sequence": view.sequence(),
            "totals": {name: total(group) for name, group in groups.items()}, "finals": rows,
            "definitions": {
                "final": "the answer post of a research delivery (typed research, or an untyped request that is not "
                         "an answer notification or notice); assignment = requested by an operator or person, "
                         "peer = requested by an agent",
                "resolvable_to_cell": "verified through an artifact pointer with a table-cell (row=;col=) or JSON-key (key=) locator",
                "number_level_pointer": "a claim or artifact pointer at the number (scope cell, claim or line)",
                "post_scoped": "no pointer at the number, but the post names evidence (shown as this post's evidence)",
                "post_scoped_value_in_named_artifact": "audit only, never displayed as a pointer: the value occurs in "
                                                       "a text artifact (<= 64 KB) the post names; bytes_absent when "
                                                       "every named artifact's bytes are outside this archive"}}
