"""Agent timelines (M4.4): one delivery on a monotonic axis.

Sources are the run folder written by `community_runtime.dispatch`: events.jsonl
(the raw harness stream, parsed with `daw.hermes.parse`), execution.json (wall and
monotonic clocks), final.md and agent-state/state.db (model-facing message bodies,
read with mode=ro). Wall time includes host sleep; monotonic time does not. A
suspension is wall − monotonic beyond the audit floor; it is drawn where the gap
between event timestamps is largest, because the stream records no sleep marker.
Token counts the provider did not report are "unavailable", never zero.

Recorded versus attributed (spec v2 C10, V6). Tool calls, exit codes and stream
compactions are recorded in the stream. Since V6 the runtime also writes run
records (`daw.commons.records`): `clock.jsonl` (heartbeats with both clocks),
`compactions.jsonl` and `receipts.json`. When they exist, suspensions are placed
between the clock records whose wall clock advanced more than their monotonic
clock, receipts are the indexed run_analysis.py receipt files, and compaction
summaries are the recorded ones: all `attributed: false`. Runs captured before
the records existed (the cohort fixture) keep the heuristics, each carrying
`attributed: true` with its rule in `basis`: the suspension (largest timestamp
gap), receipts (the exit code of the run_analysis.py call). The headline result
(first successful registration, publication or analysis) and peer answers
consumed (a post id seen in a show, inbox or verify call) are always attributed.
The web app draws attributed items in a distinct style under the legend
"attributed, not recorded"; the response's `attributed` lists their kinds and
`records` says which records the run has.
"""
import hashlib
import re
import sqlite3
from datetime import datetime

from daw import harness as harnesses
from daw import hermes
from daw.commons import records
from daw.commons.moderation import Visibility
from daw.commons.runmetrics import SUSPENSION_FLOOR_SECONDS, compactions_reported, run_metrics
from daw.util import DawError, read_json

TERMINAL = [("help", re.compile(r"(^|\s)(--help|-h)(\s|$)")), ("analysis", re.compile(r"run_analysis\.py")),
            ("register", re.compile(r"\bbio\s+register\b")), ("publish", re.compile(r"\bcommunity\s+publish\b")),
            ("fetch", re.compile(r"\bcommunity\s+fetch\b")), ("inbox", re.compile(r"\bcommunity\s+inbox\b")),
            ("search", re.compile(r"\b(community\s+search|bio\s+search)\b"))]
LANES = [("terminal:search", "search"), ("terminal:inbox", "inbox"), ("terminal:analysis", "analysis"),
         ("terminal:register", "register"), ("terminal:publish", "publish"), ("terminal:fetch", "fetch"),
         ("terminal:help", "help"), ("terminal:other", "other command"), ("file:read", "file reads"),
         ("file:write", "file writes"), ("skills", "skills"), ("memory", "memory"), ("other", "other tools")]
FILE_READS = {"read_file", "search_files", "list_files"}
FILE_WRITES = {"write_file", "patch", "edit_file"}
POST = re.compile(r"\bpost_[0-9a-f]{32}\b")
MESSAGE_COLUMNS = ("id", "session", "session_id", "role", "tool_name", "timestamp", "content")
MAX_MESSAGES = 200


def lane(item):
    name = item.get("name") or ""
    if name == "terminal":
        command = item.get("command") or ""
        for kind, pattern in TERMINAL:
            if pattern.search(command):
                return "terminal:" + kind
        return "terminal:other"
    if name in FILE_READS:
        return "file:read"
    if name in FILE_WRITES:
        return "file:write"
    if name.startswith("skill"):
        return "skills"
    if name in {"memory", "session_search"}:
        return "memory"
    return "other"


def _seconds(value):
    try:
        return datetime.fromisoformat(value).timestamp() if value else None
    except (TypeError, ValueError):
        return None


def _bounds(execution):
    return _seconds(execution.get("started")), _seconds(execution.get("finished"))


def _connect_state(folder):
    path = folder / "agent-state" / "state.db"
    if not path.is_file() or path.is_symlink():
        return None
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def state_messages(folder, execution, *, where="", params=(), offset=0, limit=50):
    """Model-facing messages in agent-state/state.db bounded by this delivery's start and finish.

    The snapshot database is cumulative per agent, so rows outside the delivery belong to
    other deliveries. Returns (items, total, columns) or (None, None, None) without a database."""
    try:
        db = _connect_state(folder)
    except sqlite3.Error:
        return None, None, None
    if db is None:
        return None, None, None
    start, end = _bounds(execution)
    try:
        with db:
            present = [r[1] for r in db.execute("PRAGMA table_info(messages)")]
            if "content" not in present:
                return None, None, None
            columns = [c for c in MESSAGE_COLUMNS if c in present]
            conditions, values = [], []
            if "timestamp" in present:
                if start is not None:
                    conditions.append("timestamp>=?")
                    values.append(start - 1)
                if end is not None:
                    conditions.append("timestamp<=?")
                    values.append(end + 1)
            if where:
                conditions.append(where)
                values.extend(params)
            clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            order = " ORDER BY " + ("timestamp," if "timestamp" in present else "") + "rowid"
            total = db.execute("SELECT count(*) FROM messages" + clause, values).fetchone()[0]
            rows = db.execute(f"SELECT {','.join(columns)} FROM messages{clause}{order} LIMIT ? OFFSET ?",
                              [*values, limit, offset]).fetchall()
    except sqlite3.Error:
        return None, None, None
    finally:
        db.close()
    return [dict(zip(columns, row, strict=True)) for row in rows], total, columns


def _script(command):
    """The analysis script named after run_analysis.py (its first non-option argument)."""
    words = command.split()
    for i, word in enumerate(words):
        if word.endswith("run_analysis.py"):
            return next((w for w in words[i + 1:] if not w.startswith("-")), None)
    return None


def _clock(parsed):
    """Map stream lines to seconds on the event axis. Lines without a timestamp take the previous stamp."""
    stamps = {e["line"]: e["event"]["timestamp"] for e in parsed["events"]
              if isinstance(e["event"].get("timestamp"), (int, float)) and not isinstance(e["event"]["timestamp"], bool)}
    if not stamps:
        lines = [e["line"] for e in parsed["events"]]
        return {line: float(i) for i, line in enumerate(lines)}, "events", None
    origin = min(stamps.values())
    positions, last = {}, 0.0
    for event in parsed["events"]:
        if event["line"] in stamps:
            last = (stamps[event["line"]] - origin) / 1000
        positions[event["line"]] = last
    return positions, "seconds", origin


def _suspension(positions, unit, suspended):
    """Place the suspension at the largest gap between consecutive stamped events; return a mapper to the monotonic axis."""
    if unit != "seconds" or not suspended:
        return None, (lambda t: t)
    ordered = sorted(set(positions.values()))
    gaps = [(b - a, a, b) for a, b in zip(ordered, ordered[1:], strict=False)]
    if not gaps:
        return ({"at": 0.0, "seconds": suspended, "gap_seconds": 0.0, "placement": "before_first_event",
                 "unplaced_seconds": suspended, "attributed": True,
                 "basis": "no gap between event timestamps to place it in"}, lambda t: t)
    gap, before, after = max(gaps)
    removed = min(suspended, gap)

    def monotonic(t):
        return t - removed if t >= after else t
    return ({"at": round(before, 3), "seconds": suspended, "gap_seconds": round(gap, 3),
             "placement": "largest_event_gap", "unplaced_seconds": round(suspended - removed, 3),
             "attributed": True, "basis": "placed at the largest gap between event timestamps; the stream "
                                          "records no sleep marker"}, monotonic)


def _recorded_suspensions(positions, unit, origin, clock):
    """Place suspensions between consecutive clock records whose wall clock advanced more than their monotonic
    clock (spec v2 V6). Inside the recorded window the break goes at the largest gap between event timestamps
    (no event can be emitted while the host sleeps). A window no wider than RECORDED_PRECISION_SECONDS of
    monotonic time is placed by record (`attributed: false`); a wider one (reindexed runs, whose only samples are
    the launch, the last heartbeat and the finish) only bounds it, so its position stays attributed.
    Returns (suspensions, mapper to the monotonic axis)."""
    windows = records.clock_windows(clock)
    if unit != "seconds" or origin is None or not windows:
        return [], (lambda t: t)
    ordered = sorted(set(positions.values()))
    first, last = (ordered[0], ordered[-1]) if ordered else (0.0, 0.0)
    placed = []
    for w in windows:
        low, high = (w["wall_from"] * 1000 - origin) / 1000, (w["wall_to"] * 1000 - origin) / 1000
        points = [low] + [p for p in ordered if low < p < high] + [high]
        gap, before, after = max((b - a, a, b) for a, b in zip(points, points[1:], strict=False))
        width = w["monotonic_to"] - w["monotonic_from"]
        entry = {"seconds": w["seconds"], "gap_seconds": round(gap, 3), "records": w["records"],
                 "window": {"from": round(low, 3), "to": round(high, 3), "monotonic_seconds": round(width, 3),
                            "sources": w["sources"]}, "precision_seconds": round(width, 3)}
        if after <= first or high <= first:
            entry.update(placement="before_first_event", at_raw=first, removed=0.0)
        elif before >= last or low >= last:
            entry.update(placement="after_last_event", at_raw=last, removed=0.0)
        else:
            entry.update(placement="clock_records" if w["precise"] else "largest_event_gap_within_clock_window",
                         at_raw=before, after_raw=after, removed=min(w["seconds"], gap))
        if w["precise"]:
            entry.update(attributed=False, basis=f"recorded: clock records {w['records'][0]} and {w['records'][1]} "
                                                 f"({round(width, 1)} s of monotonic time apart) show wall time "
                                                 f"advancing {w['seconds']} s more than monotonic time")
        else:
            entry.update(attributed=True, basis=f"the clock samples ({', '.join(w['sources'])}) only bound the "
                                                f"suspension to {round(width, 1)} s of monotonic time; inside that "
                                                "window it is placed at the largest gap between event timestamps")
        placed.append(entry)
    shifts = sorted((e["after_raw"], e["removed"]) for e in placed if e.get("removed"))

    def monotonic(t):
        return t - sum(removed for after, removed in shifts if t >= after)
    out = []
    for entry in placed:
        at = monotonic(entry.pop("at_raw"))
        entry.pop("after_raw", None)
        removed = entry.pop("removed")
        unplaced = 0.0 if entry["placement"] in ("before_first_event", "after_last_event") else entry["seconds"] - removed
        out.append({"at": round(at, 3), **entry, "unplaced_seconds": round(max(0.0, unplaced), 3)})
    return out, monotonic


def _wall_position(epoch, origin, positions, monotonic):
    """A recorded wall-clock instant (epoch seconds) on the timeline axis, or None outside the stream."""
    if origin is None or epoch is None or not positions:
        return None
    offset = epoch - origin / 1000
    if 0 <= offset <= max(positions.values()):
        return round(monotonic(offset), 3)
    return None


def _tokens(usage, answered):
    """Provider token telemetry. Missing fields are unavailable; a zero beside a real answer is unreported, not zero."""
    names = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
    if not usage:
        return {k: "unavailable" for k in names} | {"note": "no token usage was reported"}
    zero_output = usage.get("output_tokens") == 0 and answered
    out = {}
    for key in names:
        value = usage.get(key)
        out[key] = "unavailable" if value is None or (zero_output and value == 0) else value
    if zero_output:
        out["note"] = "provider reported zero output tokens beside a non-empty answer; treated as unavailable"
    return out


def _answer_posts(view, agent):
    """Answers to questions this agent asked: reading them is consuming a peer answer."""
    return {r["answer"]: r["id"] for r in view.rows(
        "SELECT r.id,r.answer FROM request r JOIN post p ON p.id=r.post WHERE p.author=? AND r.answer IS NOT NULL",
        (agent,))}


def run_list(view, *, agent=None, state=None, limit=100, offset=0, caller=None, full=False):
    """GET /api/runs: deliveries newest first, with request, task type and agent name. A request post hidden by
    moderation keeps its identity and reason; its title and kind are withheld (C2)."""
    if not 1 <= limit <= 500 or offset < 0:
        raise DawError("invalid_run_page")
    conditions, params = [], []
    if agent:
        conditions.append("a.target=?")
        params.append(view.participant(agent)["id"])
    if state:
        conditions.append("a.state=?")
        params.append(state)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    total = view.one("SELECT count(*) AS n FROM attempt a" + where, params)["n"]
    rows = view.rows("SELECT a.*,r.task_type,r.post AS request_post,r.state AS request_state,g.name AS agent_name "
                     "FROM attempt a JOIN request r ON r.id=a.request JOIN agent g ON g.id=a.target" + where
                     + " ORDER BY a.created DESC,a.id LIMIT ? OFFSET ?", [*params, limit, offset])
    vis = Visibility.of(view, caller, full)
    for row in rows:
        row.pop("path", None)
        row.update(request_hidden=vis.hidden(row["request_post"]), reason=vis.reason(row["request_post"]))
        if vis.withheld(row["request_post"]):
            row.update(request_title=None, request_kind=None)
            continue
        try:
            content = view.post(row["request_post"])["content"]
            row.update(request_title=content.get("title"), request_kind=content.get("kind"))
        except DawError:
            row.update(request_title=None, request_kind=None)
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def _withheld_posts(view, request, vis):
    """The run's request post and answer post that this caller may not read."""
    return [p for p in (request.get("post"), request.get("answer")) if p and vis.withheld(p)]


def _guard(view, run, caller, full):
    """Raw streams and model messages carry the request's text and the answer verbatim: when either post is
    hidden, they are withheld like the post itself (an operator may read them with full=true)."""
    attempt, _ = view.run_folder(run)
    request = view.one("SELECT post,answer FROM request WHERE id=?", (attempt["request"],)) or {}
    vis = Visibility.of(view, caller, full)
    withheld = _withheld_posts(view, request, vis)
    if withheld:
        raise DawError("hidden_by_moderation", ", ".join(f"{p}: {vis.reason(p)}" for p in withheld))


def run_timeline(view, run, *, caller=None, full=False):
    """GET /api/runs/{id}: the delivery timeline, its receipts, clocks and final answer.
    A hidden request post loses its title and kind; a hidden answer post withholds the final text (C2)."""
    from daw.commons.participants import describe
    attempt, folder = view.run_folder(run)
    request = view.one("SELECT * FROM request WHERE id=?", (attempt["request"],)) or {}
    vis = Visibility.of(view, caller, full)
    agent = view.participant(attempt["target"])
    execution = read_json(folder / "execution.json") if (folder / "execution.json").is_file() else {}
    name = (agent.get("config") or {}).get("harness", "hermes") if isinstance(agent.get("config"), dict) else "hermes"
    try:
        parse = harnesses.get(name).parse
    except DawError:
        parse = hermes.parse
    parsed = parse(folder / "events.jsonl")
    reported = compactions_reported(name, agent.get("config") if isinstance(agent.get("config"), dict) else None)
    metrics = run_metrics(folder, parsed, compactions_reported=reported)
    positions, unit, origin = _clock(parsed)
    clock = records.read_clock(folder)
    indexed = records.read_receipts(folder)
    recorded_compactions = records.read_compactions(folder)
    if clock is not None and len(clock) >= 2:
        suspensions, monotonic = _recorded_suspensions(positions, unit, origin, clock)
    else:
        suspension, monotonic = _suspension(positions, unit, metrics["suspended_seconds"])
        suspensions = [suspension] if suspension else []

    def at(line):
        return round(monotonic(positions[line]), 3) if line in positions else None
    answers = _answer_posts(view, agent["id"])
    calls, receipts, inbox, consumed, lanes = [], [], [], [], {}
    for item in parsed["items"]:
        if item.get("type") == "agent_message":
            continue
        kind = lane(item)
        lanes[kind] = lanes.get(kind, 0) + 1
        command = item.get("command") or ""
        target = command or item["input"].get("path") or item["input"].get("name") or ""
        call = {"line": item["line"], "result_line": item.get("result_line"), "lane": kind, "name": item.get("name"),
                "summary": str(target)[:300], "exit_code": item.get("exit_code"), "status": item.get("status"),
                "t": at(item["line"]), "t_end": at(item.get("result_line"))}
        calls.append(call)
        if kind == "terminal:analysis":
            code = item.get("exit_code")
            receipts.append({**call, "script": _script(command),
                             "outcome": "pass" if code == 0 else "unknown" if code is None else "fail",
                             "source": "exit_code", "attributed": True,
                             "basis": "exit code of the run_analysis.py call in the stream; no receipt record was "
                                      "indexed for this run"})
        if kind == "terminal:inbox":
            inbox.append({**call, "sent": "--sent" in command})
        if item.get("name") == "terminal" and re.search(r"\bcommunity\s+(show|inbox|verify)\b", command):
            mentioned = sorted(set(POST.findall(command + "\n" + str(item.get("aggregated_output") or ""))) & set(answers))
            if mentioned:
                consumed.append({**call, "posts": mentioned, "requests": [answers[p] for p in mentioned],
                                 "attributed": True,
                                 "basis": "a post id answering this agent's question appears in a show, inbox or "
                                          "verify call or its output; reading is inferred, not recorded"})
    unreceipted = []
    if indexed is not None:
        # V6: receipts are the run_analysis.py receipt files indexed for this delivery, not exit codes.
        stream_receipts, receipts = {r["line"]: r for r in receipts}, []
        for record in indexed["receipts"]:
            call = stream_receipts.get(record.get("line"))
            base = {k: v for k, v in call.items() if k not in ("outcome", "source", "attributed", "basis")} if call else {
                "line": None, "result_line": None, "lane": "terminal:analysis", "name": "run_analysis.py",
                "summary": record.get("path") or "", "exit_code": record.get("exit_code"), "status": None,
                "t": _wall_position(records.epoch(record.get("started")), origin, positions, monotonic),
                "t_end": _wall_position(records.epoch(record.get("finished")), origin, positions, monotonic)}
            receipts.append({**base, "script": record.get("producer") or base.get("script"), "outcome": record["outcome"],
                             "source": "receipt", "attributed": False,
                             "receipt": {k: record.get(k) for k in ("path", "sha256", "copy", "started", "finished",
                                                                     "exit_code", "complete", "code_unchanged",
                                                                     "verified", "found_by")}
                             | {"outputs": len(record.get("outputs") or [])}})
        matched = {r["line"] for r in receipts if r["line"] is not None}
        unreceipted = [{k: v for k, v in r.items() if k not in ("outcome", "source", "attributed", "basis")}
                       for r in stream_receipts.values() if r["line"] not in matched]
    compactions = [{"line": e["line"], "t": at(e["line"]), "source": "stream", "text": e["event"].get("text", "").strip()}
                   for e in parsed["events"] if e["event"].get("type") == "runtime_status"]
    summaries, _, _ = state_messages(folder, execution, where="content LIKE ?", params=("[CONTEXT COMPACTION%",),
                                     limit=MAX_MESSAGES)
    header, recorded_items = recorded_compactions
    compaction_summaries = []

    def place(stamp):
        if unit == "seconds" and isinstance(stamp, (int, float)) and positions:
            offset = stamp - origin / 1000
            if 0 <= offset <= max(positions.values()):
                return round(monotonic(offset), 3)
        return None
    if header is not None:
        # V6: summaries recorded at capture time (they survive without the session database); excerpts only
        # while the database is still in the run folder.
        excerpts = {hashlib.sha256((row["content"] or "").encode("utf-8", errors="replace")).hexdigest():
                    (row["content"] or "")[:400] for row in summaries or []}
        if header.get("available"):
            compaction_summaries = [{"timestamp": item.get("timestamp"), "fallback": bool(item.get("fallback")),
                                     "excerpt": excerpts.get(item.get("sha256")), "t": place(item.get("timestamp")),
                                     "message_id": item.get("message_id"), "sha256": item.get("sha256"),
                                     "source": records.COMPACTIONS_FILE} for item in recorded_items]
        summaries = recorded_items if header.get("available") else None
    else:
        for row in summaries or []:
            compaction_summaries.append({"timestamp": row.get("timestamp"),
                                         "fallback": "deterministic fallback" in (row["content"] or ""),
                                         "excerpt": (row["content"] or "")[:400], "t": place(row.get("timestamp")),
                                         "source": "state.db"})
    headline = next(({**c, "basis": "first successful " + c["lane"].split(":")[1], "attributed": True} for c in calls
                     if c["lane"] in ("terminal:register", "terminal:publish") and c["exit_code"] == 0), None)
    if headline is None:
        headline = next(({**{k: v for k, v in r.items() if k not in ("source", "receipt")},
                          "basis": "first successful analysis", "attributed": True} for r in receipts
                         if r["outcome"] == "pass" and r["t"] is not None), None)
    final_path = folder / "final.md"
    answers_text = [i["text"] for i in parsed["items"] if i.get("type") == "agent_message"]
    if final_path.is_file():
        final = {"text": final_path.read_text(errors="replace"), "source": "final.md"}
    elif answers_text:
        final = {"text": answers_text[-1], "source": "stream (no final.md: delivery did not complete)"}
    else:
        final = {"text": None, "source": None}
    duration = max(positions.values(), default=0.0)
    if request.get("answer") and vis.withheld(request["answer"]):
        final = {"text": None, "source": final["source"], "hidden": True, "reason": vis.reason(request["answer"])}
    elif request.get("answer") and vis.refused(request["answer"]):  # C5: a refused write-up's text is withheld
        final = {"text": None, "source": final["source"], "withheld": vis.refused_writeups[request["answer"]],
                 "title": vis.title(request["answer"], None)}
    content = None
    if request.get("post") and not vis.withheld(request["post"]):
        try:
            content = view.post(request["post"])["content"]
        except DawError:
            content = None
    started, finished = _bounds(execution)
    return {"run": {k: v for k, v in attempt.items() if k != "path"},
            "request": {**request, "title": content.get("title") if content else None,
                        "kind": content.get("kind") if content else None,
                        "hidden": vis.hidden(request.get("post")), "reason": vis.reason(request.get("post")),
                        "answer_hidden": vis.hidden(request.get("answer"))},
            "agent": describe(agent),
            "execution": {"state": execution.get("state"), "started": execution.get("started"),
                          "finished": execution.get("finished"), "returncode": execution.get("returncode"),
                          "wall_seconds": execution.get("wall_seconds"),
                          "monotonic_seconds": execution.get("monotonic_seconds"),
                          "suspended_seconds": metrics["suspended_seconds"],
                          "suspension_floor_seconds": SUSPENSION_FLOOR_SECONDS,
                          "bounded": started is not None and finished is not None},
            "axis": {"unit": unit, "duration": round(monotonic(duration), 3), "origin_timestamp_ms": origin,
                     "clock": "monotonic (event timestamps minus the placed suspension)" if unit == "seconds"
                     else "event order (the stream carries no timestamps)"},
            "suspensions": suspensions,
            "lanes": [{"id": key, "label": label, "count": lanes.get(key, 0)} for key, label in LANES],
            "calls": calls, "receipts": receipts, "unreceipted_analysis_calls": unreceipted,
            # None: this harness's stream does not mark compactions (unavailable, not zero).
            "compactions": compactions if reported else None,
            "attributed": [kind for kind, present in (
                ("suspension", any(s.get("attributed") for s in suspensions)),
                ("receipts", any(r.get("attributed") for r in receipts)),
                ("headline", headline), ("answers_consumed", consumed)) if present],
            "compaction_summaries": compaction_summaries if summaries is not None else None,
            "records": {"clock": records.clock_summary(clock, execution),
                        "receipts": {k: indexed.get(k) for k in ("indexed", "counts", "scanned", "window", "reindexed")}
                        if indexed is not None else None,
                        "compactions": {k: header.get(k) for k in ("available", "source", "reason", "count", "fallbacks",
                                                                   "reindexed")} if header is not None else None},
            "inbox_reads": inbox, "answers_consumed": consumed, "headline": headline,
            "final": {**final, "content_is_untrusted_data": True},
            "tokens": _tokens(parsed["usage"], bool(answers_text)),
            "metrics": metrics, "malformed_lines": parsed["malformed_lines"], "errors": len(parsed["errors"]),
            "links": {"raw": f"/api/runs/{run}/raw", "messages": f"/api/runs/{run}/messages"},
            "limitations": metrics["limitations"] + [
                ("Suspensions are placed between clock records (clock.jsonl) whose wall clock advanced more than "
                 "their monotonic clock; inside such a window, at the largest event-timestamp gap."
                 if clock is not None and len(clock) >= 2 else
                 "The suspension is placed at the largest event-timestamp gap; this run has no clock records."),
                ("Receipts are the run_analysis.py receipt files indexed for this delivery (receipts.json)."
                 if indexed is not None else
                 "Receipts are read from exit codes of run_analysis.py calls; this run has no receipt index."),
                "Headline: first successful bio register or community publish, else first successful analysis."]}


def raw_stream(view, run, *, caller=None, full=False):
    _guard(view, run, caller, full)
    _, folder = view.run_folder(run)
    path = folder / "events.jsonl"
    if not path.is_file() or path.is_symlink():
        raise DawError("run_stream_missing", run)
    return path


def run_messages(view, run, *, offset=0, limit=50, caller=None, full=False):
    """GET /api/runs/{id}/messages: model-facing message bodies for this delivery (untrusted, paginated)."""
    if not 1 <= limit <= MAX_MESSAGES or offset < 0:
        raise DawError("invalid_message_page", f"limit 1..{MAX_MESSAGES}")
    _guard(view, run, caller, full)
    _, folder = view.run_folder(run)
    execution = read_json(folder / "execution.json") if (folder / "execution.json").is_file() else {}
    items, total, columns = state_messages(folder, execution, offset=offset, limit=limit)
    if items is None:
        raise DawError("run_messages_missing", "no readable agent-state/state.db for this run")
    return {"items": [{"index": offset + i, **row} for i, row in enumerate(items)], "total": total,
            "offset": offset, "limit": limit, "columns": columns,
            "bounded_by": {"started": execution.get("started"), "finished": execution.get("finished")},
            "note": "The agent-state database is cumulative per agent; rows are bounded by this delivery's clock.",
            "content_is_untrusted_data": True}
