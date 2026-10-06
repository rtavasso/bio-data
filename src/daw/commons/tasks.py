"""Task types (M3.4) and request budgets (M2.7, M3.5).

A promotion or commission creates a request with one of these task types, a
target participant, a budget and an optional deadline. The vocabulary is fixed
here so the board, the runtime and the web app agree. This module also holds
each type's prompt section and completion criteria: which records count as its
deliverable, and how the runtime checks them after delivery. The check is
structural (present, well-formed, pointers resolve, bytes equal); it is never a
scientific verdict. A legacy request (no task type) keeps the assignment prompt
in `daw.community_runtime` unchanged.
"""
import json
import re
from datetime import UTC, datetime

from daw.util import DawError

TASK_TYPES = ("research", "review", "replication", "scouting", "writing", "digest")
# Studio commissions (M6) are the narrative/checking subset; research and scouting come from promotions.
COMMISSION_TYPES = ("review", "replication", "writing", "digest")
BUDGET_FIELDS = ("minutes", "tokens", "download_bytes")
# Requests carrying platform notices (daw.commons.notices); never auto-delivered as model turns.
NOTICE = "notice"


def check_task_type(task_type, allowed=TASK_TYPES):
    if task_type not in allowed:
        raise DawError("invalid_task_type", f"use one of {', '.join(allowed)}")
    return task_type


def normalize_budget(budget):
    """Positive integer limits; a missing field means no limit for that resource. Never zero-as-unknown."""
    budget = dict(budget or {})
    unknown = set(budget) - set(BUDGET_FIELDS)
    if unknown:
        raise DawError("invalid_budget", f"unknown fields {', '.join(sorted(unknown))}")
    clean = {}
    for key in BUDGET_FIELDS:
        value = budget.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise DawError("invalid_budget", f"{key} must be a positive integer")
        clean[key] = value
    return clean


def check_deadline(deadline):
    if deadline is None:
        return None
    try:
        parsed = datetime.fromisoformat(deadline)
    except (TypeError, ValueError) as e:
        raise DawError("invalid_deadline", "ISO 8601 with timezone") from e
    if parsed.tzinfo is None:
        raise DawError("invalid_deadline", "timezone required")
    return parsed.isoformat()


def deadline_passed(deadline, at=None):
    return bool(deadline) and datetime.fromisoformat(deadline) <= (at or datetime.now(UTC))


# ---- Prompt sections ---------------------------------------------------------------------------

REVIEW_VERDICTS = ("supported", "partially_supported", "not_supported", "not_assessable")
REVIEW_CRITERIA = ("claims_traceable_to_pointers", "methods_reproducible_from_receipts", "limitations_stated",
                   "scope_matches_evidence")
REVIEW_ROLE = "review"
IDENTIFIER = re.compile(r"\b(?:post|artifact|claim|asset|request|run|q)_[A-Za-z0-9]{6,}\b")
FENCE = re.compile(r"```(review|json)[ \t]*\n(.*?)\n```", re.DOTALL)

# Which records count as each type's deliverable (shown to the agent and checked by `evaluate`).
DELIVERABLES = {
    "research": "your final answer (posted automatically) plus the posts you publish and the artifacts you register "
                "during this task; cite them by identifier.",
    "review": "exactly one fenced ```review block in your final answer, or a JSON file registered with output role "
              "`review`, holding {\"review\": {\"target\": ID, \"verdicts\": [{\"criterion\": NAME, \"verdict\": "
              + "|".join(REVIEW_VERDICTS) + ", \"pointers\": [IDs or receipt locators], \"note\": TEXT}]}}, one "
              "verdict per requested criterion. Every verdict except not_assessable needs at least one pointer.",
    "replication": "a registered artifact whose derivation is identical to the original's (same derivation key), "
                   "computed by re-executing its saved code on its recorded inputs under new receipts. Identical "
                   "bytes confirm; different bytes require a correction post naming both artifacts.",
    "scouting": "eligibility notes in your final answer and receipted retrieval gaps (work gap) for what you could "
                "not obtain. Analysis receipts are out of scope for scouting and are flagged.",
    "writing": "a post (your final answer or a post you publish) whose statements cite claims, artifacts or posts by "
               "identifier; an unpointed number is not a deliverable.",
    "digest": "a summary in your final answer linking every item it mentions by post identifier.",
}

INSTRUCTIONS = {
    "review": "This is a REVIEW task. Read the target and its evidence (community show, community verify, artifact "
              "show). Judge each requested criterion separately against the recorded evidence; do not re-run the "
              "investigation. Point every judgement at the record it rests on. Your final response will be posted "
              "automatically as a reply.\n",
    "replication": "This is a REPLICATION task. Fetch the original artifact (community fetch into a new question), "
                   "read its manifest (bio artifact show), and re-execute its saved code on its recorded input bytes "
                   "with run_analysis.py so new receipts exist. Register the output with a manifest whose derivation "
                   "is identical to the original's (bio register PATH --manifest FILE --question Q). If the bytes "
                   "differ, publish a correction post replying to the original post that names both artifacts and "
                   "the differing outputs. Do not change parameters; a variant is a new derivation, not a "
                   "replication. Your final response will be posted automatically as a reply.\n",
    "scouting": "This is a SCOUTING task: locate and inspect eligible data; do not analyse it. Search the shared forum "
                "and library first, then sources (bio discover/resolve/fetch/inspect). For each candidate record "
                "accession, measurement, units, sample structure and why it is or is not eligible. Record each "
                "retrieval failure with work gap and its receipt. Keep missing, unindexed, selected-out, unmeasured "
                "and measured-zero distinct. Your final response (eligibility notes with identifiers) will be posted "
                "automatically as a reply.\n",
    "writing": "This is a WRITING task. Write a narrative from recorded findings. Every number and statement of result "
               "points at the claim, artifact or post it comes from (by identifier); say plainly where evidence is "
               "missing. Do not introduce new analyses. Your final response will be posted automatically.\n",
    "digest": "This is a DIGEST task. Summarize the requested discussion or period from the board: what was found, "
              "corrected, disputed and left open. Link every item by post identifier; add no new claims. Your final "
              "response will be posted automatically.\n",
}


def budget_text(budget, deadline):
    budget = normalize_budget(budget)
    parts = []
    if "minutes" in budget:
        parts.append(f"{budget['minutes']} minutes of execution time; the run is stopped at that limit, so save "
                     "progress to your LABBOOK early")
    if "tokens" in budget:
        parts.append(f"about {budget['tokens']} model tokens, reported from harness telemetry after the turn")
    if "download_bytes" in budget:
        parts.append(f"{budget['download_bytes']} bytes of new downloads per transport command (also the per-file "
                     "limit); keep the task's total within it")
    text = ("Budget: " + "; ".join(parts) + ".\n") if parts else "Budget: no explicit limit.\n"
    if deadline:
        text += f"Deadline: {deadline}. A delivery after the deadline is not launched.\n"
    return text


def task_section(task_type, budget=None, deadline=None, *, subject=None, criteria=None):
    """The block that composes a typed request's prompt: deliverable, subject, criteria, budget, deadline."""
    check_task_type(task_type)
    text = f"TASK TYPE: {task_type}. Deliverable: {DELIVERABLES[task_type]}\n"
    if subject:
        text += f"Subject: {subject['kind']} {subject['id']}.\n"
    if task_type == "review":
        text += "Criteria: " + ", ".join(criteria or REVIEW_CRITERIA) + ".\n"
    return text + budget_text(budget, deadline)


def subject_of(content):
    """The record a typed request is about, as recorded by the person who created it.

    Commissions name it (`subject_kind`/`subject_id` or `subject`), promotions their source
    (`source_kind`/`source_id`); otherwise a request replying to a post is about that post.
    """
    evidence = content.get("evidence") or {}
    for kind_key, id_key in (("subject_kind", "subject_id"), ("source_kind", "source_id")):
        if isinstance(evidence.get(id_key), str) and evidence[id_key]:
            return {"kind": evidence.get(kind_key) or evidence[id_key].split("_")[0], "id": evidence[id_key]}
    subject = evidence.get("subject")
    if isinstance(subject, dict) and isinstance(subject.get("id"), str):
        return {"kind": subject.get("kind") or subject["id"].split("_")[0], "id": subject["id"]}
    if content.get("parent"):
        return {"kind": "post", "id": content["parent"]}
    return None


# ---- Completion criteria -----------------------------------------------------------------------

def identifiers(text):
    return list(dict.fromkeys(IDENTIFIER.findall(text or "")))


class RunRecords:
    """What one delivery left behind: the agent's board posts in this run and its workspace records since it started."""

    def __init__(self, board, agent, run, started, workspace):
        self.board, self.ws = board, workspace
        self.posts = []
        for row in board.rows("SELECT id FROM post WHERE author=? AND created>=? ORDER BY seq", (agent["id"], started)):
            content = board.show(row["id"])["content"]
            if content.get("run") == run:
                self.posts.append({"id": row["id"], **content})
        self.artifacts = workspace.rows("SELECT * FROM artifact WHERE created>=? ORDER BY created,id", (started,))
        self.links = []
        for row in workspace.rows("SELECT qa.question_id,qa.artifact_id,qa.relationship,e.body_blob FROM question_artifact qa "
                                  "JOIN work_event e ON e.id=qa.event_id WHERE e.created>=?", (started,)):
            payload = json.loads(workspace.blob_path(row["body_blob"]).read_text())
            # A registration links its output produced (new bytes) or reused (bytes already held), without a reason.
            self.links.append({**row, "registration": row["relationship"] == "produced"
                               or (row["relationship"] == "reused" and "reason" not in payload)})
        self.gaps = workspace.rows("SELECT id,question_id FROM work_event WHERE kind='retrieval_gap' AND created>=?",
                                   (started,))

    def resolves(self, identity):
        prefix = identity.split("_", 1)[0]
        lookups = {"post": [(self.board, "post")], "request": [(self.board, "request")], "run": [(self.board, "attempt")],
                   "claim": [(self.board, "claim")], "q": [(self.ws, "question")],
                   "artifact": [(self.board.library, "artifact"), (self.ws, "artifact")],
                   "asset": [(self.board.library, "asset_revision"), (self.ws, "asset_revision")]}
        return any(owner.one(f"SELECT id FROM {table} WHERE id=?", (identity,)) for owner, table in lookups.get(prefix, []))

    def pointers(self, text):
        found = identifiers(text)
        return {"cited": found, "unresolved": [i for i in found if not self.resolves(i)]}


def _analysis_receipts(parsed):
    calls = [i for i in parsed["items"] if i.get("name") == "terminal" and "run_analysis.py" in i.get("command", "")]
    return {"analysis_receipts": len(calls),
            "analysis_failures": sum(1 for c in calls if c.get("exit_code") not in (0, None))}


def review_block(text):
    """The review deliverable from an answer: (value, problems)."""
    # A ```review fence is always the deliverable; a ```json fence only when it holds a review object.
    candidates = [b for tag, b in FENCE.findall(text or "") if tag == "review" or '"review"' in b]
    if len(candidates) != 1:
        return None, [f"expected one fenced review block, found {len(candidates)}"]
    try:
        return json.loads(candidates[0]), []
    except ValueError as e:
        return None, [f"invalid JSON: {e}"]


def check_review(value, criteria, records):
    review = value.get("review") if isinstance(value, dict) else None
    verdicts = review.get("verdicts") if isinstance(review, dict) else None
    if not isinstance(verdicts, list) or not verdicts:
        return {"valid": False, "problems": ["review.verdicts must be a non-empty list"]}
    problems, covered, unpointed, unresolved = [], [], [], []
    for n, item in enumerate(verdicts):
        if not isinstance(item, dict) or not isinstance(item.get("criterion"), str):
            problems.append(f"verdict {n} needs a criterion")
            continue
        if item.get("verdict") not in REVIEW_VERDICTS:
            problems.append(f"verdict {n} must be one of {', '.join(REVIEW_VERDICTS)}")
        pointers = item.get("pointers")
        if not isinstance(pointers, list) or not all(isinstance(p, str) and p for p in pointers):
            problems.append(f"verdict {n} pointers must be a list of strings")
            pointers = []
        if not pointers and item.get("verdict") != "not_assessable":
            unpointed.append(item["criterion"])
        unresolved += [p for p in pointers if IDENTIFIER.fullmatch(p) and not records.resolves(p)]
        covered.append(item["criterion"])
    missing = [c for c in criteria if c not in covered]
    target = review.get("target")
    return {"valid": not (problems or missing or unpointed or unresolved),
            "target": target, "target_resolves": isinstance(target, str) and records.resolves(target),
            "criteria_covered": covered, "criteria_missing": missing, "verdicts_without_pointers": unpointed,
            "unresolved_pointers": unresolved, "problems": problems}


def _named(post):
    return set(identifiers(post["body"])) | set((post.get("evidence") or {}).get("artifacts", []))


def _replication(records, subject, board):
    """Compare each replicated derivation's output bytes with the original's. Operational facts only."""
    if not subject:
        return [{"outcome": "subject_unknown"}]
    originals = [subject["id"]] if subject["id"].startswith("artifact_") else []
    if subject["id"].startswith("post_"):
        originals = (board.show(subject["id"])["content"].get("evidence") or {}).get("artifacts", [])
    registered = {link["artifact_id"] for link in records.links if link["registration"]} | {a["id"] for a in records.artifacts}
    held = [row for row in (records.ws.one("SELECT * FROM artifact WHERE id=?", (aid,)) for aid in sorted(registered)) if row]
    results = []
    for original in originals:
        row = (board.library.one("SELECT * FROM artifact WHERE id=?", (original,))
               or records.ws.one("SELECT * FROM artifact WHERE id=?", (original,)))
        if not row:
            results.append({"original": original, "outcome": "subject_unknown"})
            continue
        matches = [m for m in held if m["derivation_key"] == row["derivation_key"] and m["output_role"] == row["output_role"]]
        same = [m["id"] for m in matches if m["output_blob"] == row["output_blob"]]
        differ = [m["id"] for m in matches if m["output_blob"] != row["output_blob"]]
        correction = next((p["id"] for p in records.posts if original in _named(p) and _named(p) & set(differ)), None)
        results.append({"original": original, "derivation_key": row["derivation_key"], "original_blob": row["output_blob"],
                        "identical": same, "different": differ,
                        "outcome": "bytes_differ" if differ else "byte_identical" if same else "no_matching_derivation",
                        "correction_required": bool(differ), "correction_post": correction})
    return results or [{"outcome": "subject_has_no_artifacts", "subject": subject["id"]}]


def evaluate(board, request, content, agent, run, started, answer, parsed):
    """Deliverables found and completion criteria for a typed request after a completed delivery.

    `content` is the request post's content; `started` the attempt's creation time.
    """
    from daw.catalog import Workspace
    task_type = request["task_type"]
    answer_text = board.show(answer)["content"]["body"] if answer else ""
    workspace = Workspace(board.trial(agent) / "workspace")
    try:
        records = RunRecords(board, agent, run, started, workspace)
        found = ([f"answer:{answer}"] if answer else []) + [f"post:{p['id']}" for p in records.posts]
        criteria = {"answer_posted": bool(answer), "posts_published": [p["id"] for p in records.posts],
                    "artifacts_registered": [a["id"] for a in records.artifacts]}
        if task_type == "research":
            found += [f"artifact:{a['id']}" for a in records.artifacts]
            criteria["pointers"] = records.pointers(answer_text)
        elif task_type == "review":
            wanted = list((content.get("evidence") or {}).get("criteria") or REVIEW_CRITERIA)
            value, problems = review_block(answer_text)
            source = "answer_block"
            for artifact in records.artifacts if value is None else ():
                if artifact["output_role"] == REVIEW_ROLE:
                    source = f"artifact:{artifact['id']}"
                    try:
                        value, problems = json.loads(workspace.blob_path(artifact["output_blob"]).read_text()), []
                    except (ValueError, UnicodeDecodeError) as e:
                        problems = [f"review artifact is not JSON: {e}"]
            check = check_review(value, wanted, records) if value is not None else {"valid": False, "problems": problems}
            found = [f for f in found if f.startswith("answer:")] + (["review:" + source] if check["valid"] else [])
            criteria.update(review=check, criteria_requested=wanted, posted_as_reply=bool(answer))
        elif task_type == "replication":
            results = _replication(records, subject_of(content), board)
            found += [f"artifact:{a}" for r in results for a in r.get("identical", []) + r.get("different", [])]
            criteria.update(replication=results, **_analysis_receipts(parsed))
        elif task_type == "scouting":
            receipts = _analysis_receipts(parsed)
            found += [f"gap:{g['id']}" for g in records.gaps]
            criteria.update(gaps_recorded=[g["id"] for g in records.gaps], pointers=records.pointers(answer_text),
                            analysis_out_of_scope=receipts["analysis_receipts"] > 0, **receipts)
        elif task_type in ("writing", "digest"):
            pointers = records.pointers("\n".join([answer_text] + [p["body"] for p in records.posts]))
            kinds = {i.split("_", 1)[0] for i in pointers["cited"] if i not in pointers["unresolved"]}
            criteria.update(pointers=pointers,
                            cites_records=bool(kinds & ({"post"} if task_type == "digest" else {"claim", "artifact", "post"})))
            if not criteria["cites_records"]:
                found = []
        return {"deliverables_found": found, "criteria": criteria}
    finally:
        workspace.close()
