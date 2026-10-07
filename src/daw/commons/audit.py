"""Operator audit log (spec v2 V9): board events filtered by kind, participant and time, newest first.

`GET /api/audit` (operators: permission `audit`) pages the immutable board event log with SQL filters:
`kind` (one or more, comma-separated), `participant` (an id or name, matched against the participant fields
an event body records: author, actor, agent, target, reader, participant, uploader, addressee, issuer),
`since`/`until` (ISO 8601, compared as instants) and a `before` cursor (the smallest sequence of the previous
page). Event bodies are framed through `moderation.Visibility` like the SSE stream, so a hidden post's text
stays withheld unless the operator asks for `full`. Facets count events per kind under the same filters.
Read-only.
"""
from daw.commons.permissions import require
from daw.commons.savedviews import PARTICIPANT_FIELDS, instant
from daw.util import DawError

MAX_LIMIT = 500


def audit_log(view, caller, *, kinds=None, participant=None, since=None, until=None, before=None, limit=100,
              full=False):
    from daw.commons.moderation import Visibility
    from daw.commons.views import _jsonish
    if caller is None:
        raise DawError("authentication_required", "the audit log is for operators")
    require(view, caller, "audit")
    if not 1 <= limit <= MAX_LIMIT or (before is not None and before < 1):
        raise DawError("invalid_page_bounds", f"1 <= limit <= {MAX_LIMIT}; before >= 1")
    conditions, params = [], []
    wanted = sorted({k.strip() for k in (kinds or []) if k and k.strip()})
    if wanted:
        conditions.append(f"kind IN ({','.join('?' * len(wanted))})")
        params += wanted
    person = None
    if participant:
        person = view.participant(participant)["id"]
        conditions.append("(" + " OR ".join(f"json_extract(body,'$.{f}')=?" for f in PARTICIPANT_FIELDS) + ")")
        params += [person] * len(PARTICIPANT_FIELDS)
    start, end = instant(since, "since"), instant(until, "until")
    if start:
        conditions.append("julianday(created) >= julianday(?)")
        params.append(start.isoformat())
    if end:
        conditions.append("julianday(created) <= julianday(?)")
        params.append(end.isoformat())
    where = " AND ".join(conditions) or "1"
    facets = {row["kind"]: row["n"] for row in view.rows(
        f"SELECT kind,count(*) AS n FROM event WHERE {where} GROUP BY kind ORDER BY n DESC,kind", params)}
    paged = where + (" AND seq < ?" if before is not None else "")
    rows = view.rows(f"SELECT * FROM event WHERE {paged} ORDER BY seq DESC LIMIT ?",
                     params + ([before] if before is not None else []) + [limit + 1])
    more = len(rows) > limit
    rows = rows[:limit]
    vis = Visibility.of(view, caller, full)
    items = [vis.event({**row, "body": _jsonish(row["body"], {})}) for row in rows]
    return {"items": items, "total": sum(facets.values()), "facets": facets,
            "kinds": [r["kind"] for r in view.rows("SELECT DISTINCT kind FROM event ORDER BY kind")],
            "filters": {"kind": wanted, "participant": person, "since": start.isoformat() if start else None,
                        "until": end.isoformat() if end else None, "before": before, "limit": limit},
            "next_before": items[-1]["seq"] if more and items else None, "sequence": view.sequence(),
            "login_failures_recorded": (view.one("SELECT count(*) AS n FROM login_failure")["n"] if view.one(
                "SELECT 1 AS x FROM sqlite_master WHERE type='table' AND name='login_failure'") else None),
            "note": "Immutable board events; participant matches recorded body fields only."}
