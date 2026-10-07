"""Lightweight question events and transparent retrieval-gap aggregation."""
from collections import Counter
from datetime import datetime

from daw.util import DawError, read_json


def validate_gap(payload, question):
    if not isinstance(payload, dict):
        raise DawError("invalid_retrieval_gap", "use a JSON object")
    for field in ("desired_information", "why_current_tools_failed"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise DawError("invalid_retrieval_gap", f"{field} must describe the actual retrieval failure")
    for field in ("source_or_format", "likely_value", "possible_indexing_solution", "gap_key"):
        if field in payload and (not isinstance(payload[field], str) or not payload[field].strip()):
            raise DawError("invalid_retrieval_gap", f"{field} must be nonempty text when supplied")
    if payload.get("question", question) != question:
        raise DawError("retrieval_gap_question_mismatch")
    # Extra fields survive. This is a research note, not a scientific ontology.
    return {**payload, "question": question, "source_or_format": payload.get("source_or_format", "unspecified")}


def validate_withdrawal(ws, payload, question):
    if not isinstance(payload, dict) or not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
        raise DawError("invalid_gap_withdrawal", "provide the gap event ID and a reason")
    if not isinstance(payload.get("event"), str):
        raise DawError("invalid_gap_withdrawal_target", "provide a retrieval_gap event ID")
    target = ws.one("SELECT * FROM work_event WHERE id=?", (payload["event"],))
    if not target or target["kind"] != "retrieval_gap" or target["question_id"] != question:
        raise DawError("invalid_gap_withdrawal_target", "withdraw a retrieval_gap from this question")
    return {**payload, "question": question}


def report_gaps(ws, *, question=None, since=None, source=None, limit=20, max_events=10000):
    if not 1 <= limit <= 100 or not 1 <= max_events <= 100000:
        raise DawError("invalid_gap_report_bounds", f"limit must be 1..100 and max_events 1..100000 "
                       f"(got limit={limit}, max_events={max_events})")
    conditions, params = ["kind='retrieval_gap'"], []
    if question:
        if not ws.one("SELECT id FROM question WHERE id=?", (question,)):
            raise DawError("unknown_question", question)
        conditions.append("question_id=?")
        params.append(question)
    if since:
        try:
            stamp = datetime.fromisoformat(since)
            if stamp.tzinfo is None:
                raise ValueError("timezone required")
        except ValueError as e:
            raise DawError("invalid_gap_since", "use an ISO 8601 timestamp with timezone") from e
        conditions.append("julianday(created)>=julianday(?)")
        params.append(stamp.isoformat())
    where = " AND ".join(conditions)
    total = ws.one("SELECT count(*) AS n FROM work_event WHERE " + where, params)["n"]
    rows = ws.rows("SELECT * FROM work_event WHERE " + where + " ORDER BY created DESC,id DESC LIMIT ?", params + [max_events])
    # Corrections can be newer than the selected gap window. Preserve both
    # records, and never rank a disputed/withdrawn report as an observed failure.
    correction_rows = ws.rows("SELECT * FROM work_event WHERE kind IN "
                              "('retrieval_gap_withdrawal','retrieval_gap_correction') "
                              + ("AND question_id=? " if question else "")
                              + "ORDER BY created DESC,id DESC LIMIT ?",
                              ([question] if question else []) + [max_events + 1])
    corrections, withdrawals = {}, {}
    invalid_corrections = []
    for event in correction_rows[:max_events]:
        payload = read_json(ws.blob_path(event["body_blob"]))
        target = payload.get("event", payload.get("supersedes_event")) if isinstance(payload, dict) else None
        original = ws.one("SELECT * FROM work_event WHERE id=?", (target,)) if isinstance(target, str) else None
        if not original or original["kind"] != "retrieval_gap" or original["question_id"] != event["question_id"]:
            invalid_corrections.append(event["id"])
            continue
        detail = {"event": event["id"], "body_blob": event["body_blob"], "payload": payload}
        if event["kind"] == "retrieval_gap_withdrawal":
            try:
                validate_withdrawal(ws, payload, event["question_id"])
            except DawError:
                invalid_corrections.append(event["id"])
                continue
            withdrawals.setdefault(target, []).append(detail)
        else:
            corrections.setdefault(target, []).append(detail)
    groups, legacy, matched, withdrawn, disputed = {}, [], 0, [], []
    for event in rows:
        raw = read_json(ws.blob_path(event["body_blob"]))
        try:
            payload = validate_gap(raw, event["question_id"])
        except DawError as e:
            # Preserve pre-v3 freeform events and expose them for follow-up.
            legacy.append({"event": event["id"], "question": event["question_id"], "body_blob": event["body_blob"], "reason": str(e)})
            continue
        fmt = " ".join(payload["source_or_format"].casefold().split())
        if source and fmt != " ".join(source.casefold().split()):
            continue
        if event["id"] in withdrawals or event["id"] in corrections:
            detail = {"event": event["id"], "question": event["question_id"], "body_blob": event["body_blob"],
                      "withdrawals": withdrawals.get(event["id"], []), "corrections": corrections.get(event["id"], [])}
            (withdrawn if event["id"] in withdrawals else disputed).append(detail)
            continue
        matched += 1
        key = " ".join(payload.get("gap_key", payload["desired_information"]).casefold().split())
        group = groups.setdefault((fmt, key), {"source_or_format": fmt, "gap_key": key, "observations": 0,
            "questions": set(), "reported_value": Counter(), "proposed_solutions": set(), "examples": [],
            "latest": event["created"], "earliest": event["created"]})
        group["observations"] += 1
        group["questions"].add(event["question_id"])
        group["earliest"] = event["created"]
        group["reported_value"][payload.get("likely_value", "unassessed")] += 1
        if payload.get("possible_indexing_solution"):
            group["proposed_solutions"].add(payload["possible_indexing_solution"])
        if len(group["examples"]) < 3:
            group["examples"].append({"event": event["id"], "body_blob": event["body_blob"], "payload": payload,
                                      "verification": "author-reported; inspect actual tool results and receipt bytes"})
    output = []
    for group in groups.values():
        group["distinct_questions"] = len(group["questions"])
        group["questions"] = sorted(group["questions"])
        group["reported_value"] = dict(group["reported_value"])
        group["proposed_solutions"] = sorted(group["proposed_solutions"])
        output.append(group)
    output.sort(key=lambda g: (-g["distinct_questions"], -g["observations"], g["source_or_format"], g["gap_key"]))
    return {"groups": output[:limit], "total_groups": len(output), "matching_events": matched,
        "events_in_scope": total, "events_scanned": len(rows), "scan_complete": total == len(rows),
        "groups_truncated": len(output) > limit, "unstructured_events": legacy[:limit], "unstructured_count": len(legacy),
        "withdrawn_events": withdrawn, "withdrawn_count": len(withdrawn),
        "corrections_requiring_review": disputed, "corrected_count": len(disputed),
        "correction_scan_complete": len(correction_rows) <= max_events, "invalid_corrections": invalid_corrections,
        "filters": {"question": question, "since": since, "source_or_format": source},
        "ranking": "distinct questions, then author-reported observations; not verified failures or a scientific score",
        "grouping": "normalized source/format plus explicit gap_key or exact desired_information; no semantic merging",
        "content_is_untrusted_data": True}
