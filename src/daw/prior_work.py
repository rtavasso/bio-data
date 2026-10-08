"""Other participants' work a question has drawn on, read from the question's own records.

A question records every `community fetch` (event `community_evidence_fetched`: the post, its author and the
artifacts it carried) and every `artifact use` (`question_artifact` relationship `considered` or `reused`, with
the reason). This module joins them so an agent sees, at the start of a turn and before it posts, whose work it
is building on, and so a final answer that relies on a peer's artifact can be checked for crediting it. Round
three: answers that leaned on a peer's tables pointed their ledger claims only at the author's own artifacts, so
the peer's contribution was invisible in the ledger.
"""
from daw.util import read_json

RANK = {"considered": 1, "reused": 2, "produced": 3}


def prior_work(ws, qid):
    """[{artifact, post, author, relationship, reason}] for artifacts this question fetched from the board, most
    committed relationship first (reused before considered). Artifacts the question produced itself are omitted."""
    fetched = {}
    for row in ws.rows("SELECT body_blob FROM work_event WHERE question_id=? AND kind='community_evidence_fetched' "
                       "ORDER BY created,id", (qid,)):
        try:
            payload = read_json(ws.blob_path(row["body_blob"]))
        except (OSError, ValueError):
            continue
        roots = payload.get("artifacts") or []
        roots = roots if isinstance(roots, list) else list(roots)
        for aid in roots:
            if isinstance(aid, str):
                fetched.setdefault(aid, {"post": payload.get("post"), "author": payload.get("author")})
    links = {}
    for row in ws.rows("SELECT artifact_id, relationship, event_id FROM question_artifact WHERE question_id=?", (qid,)):
        current = links.get(row["artifact_id"])
        if current is None or RANK.get(row["relationship"], 0) > RANK.get(current["relationship"], 0):
            links[row["artifact_id"]] = {"relationship": row["relationship"], "event": row["event_id"]}
    out = []
    for aid, link in links.items():
        if link["relationship"] == "produced" or aid not in fetched:
            continue
        reason = None
        event = ws.one("SELECT body_blob FROM work_event WHERE id=?", (link["event"],))
        if event:
            try:
                reason = read_json(ws.blob_path(event["body_blob"])).get("reason")
            except (OSError, ValueError):
                reason = None
        out.append({"artifact": aid, **fetched[aid], "relationship": link["relationship"], "reason": reason})
    out.sort(key=lambda r: (-RANK.get(r["relationship"], 0), r["artifact"]))
    return out


def uncredited(prior, text, claims=()):
    """Reused prior artifacts that neither the text nor any claim pointer names (by artifact id or source post)."""
    named = set()
    for claim in claims or ():
        for pointer in claim.get("pointers", []) if isinstance(claim, dict) else []:
            pid = str(pointer.get("id", ""))
            named.add(pid.split("#", 1)[0])
    missing = []
    for item in prior:
        if item["relationship"] != "reused":
            continue
        ids = {item["artifact"], item.get("post")}
        if any(i and (i in text or i in named) for i in ids):
            continue
        missing.append(item)
    return missing
