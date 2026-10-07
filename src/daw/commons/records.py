"""Delivery records for what the timeline used to attribute (spec v2 V6, v3 B10, G3, V13).

The runtime writes these records into each run folder at capture time, beside the harness's own stream:

- `clock.jsonl` (written by `daw.agent_capture.execute` while the harness runs): heartbeat records with
  both clocks at a fixed cadence. Consecutive records whose wall clock advanced much more than their
  monotonic clock bracket a host suspension, so the timeline places it by record instead of by the largest
  gap between event timestamps. events.jsonl is never touched (see `agent_capture.ClockRecords`).
- `compactions.jsonl`: after the turn, the compaction summaries the harness wrote to its session store
  during the delivery window (source row id, timestamp, size and sha256), read from the run's own session
  snapshot (`adapter.compaction_store`: the Hermes session database, or Claude Code's session transcripts). A
  summary is labelled the deterministic fallback by a marker match (`is_fallback`: Hermes's fallback `## Goal`), never
  by a harness signal; the header and every item say so. Each summary is also a `compaction_observed` board
  event (v3 B10) carrying the source row id and its length as captured. A harness whose session state does
  not expose summaries gets a header line with `available: false` and the reason: unavailable, never zero.
- `receipts.json` plus `receipts/<sha256>.json`: run_analysis.py receipt files written during the delivery,
  found in the agent's checkout by the paths its run_analysis.py calls named and by a scan of the
  question folders, kept only when the receipt's own start and finish fall inside the delivery window and
  its working directory is not another participant's. Each is hashed, copied (immutable, content
  addressed) and checked against what exists now: the producer's current bytes, the outputs' current bytes,
  and the sha256 run_analysis.py printed into the stream. A board event `receipts_indexed` records the
  indexing.
- `turn_economics.json` (v3 V13, `daw.commons.economics`): what the turn cost and where its context went.

`bio commons runs reindex RUN` builds the same records for runs captured before they existed, only from what
the run folder and the checkout still hold (v3 G3). Clock records come from samples that pair both clocks:
execution.json's start and finish, heartbeat.json's last sample, and, where those samples show a suspension,
the stream's own event timestamps on either side of the only gap between stamped events long enough to hold it
(`reindex_clock`). Every reindexed record says `reindexed: true` and names its source; nothing is
interpolated, and a window the samples cannot narrow stays coarse, so its suspension is still placed by a
heuristic and stays attributed. Records are append-only: an existing record file is never rewritten.
"""
import hashlib
import json
import re
import shlex
import sqlite3
from datetime import datetime
from pathlib import Path

from daw.agent_capture import CLOCK_FILE
from daw.util import DawError, file_hash, now, read_json, write_json

RECEIPTS_FILE = "receipts.json"
RECEIPT_DIR = "receipts"
COMPACTIONS_FILE = "compactions.jsonl"
ECONOMICS_FILE = "turn_economics.json"
RECORD_FILES = (CLOCK_FILE, COMPACTIONS_FILE, RECEIPTS_FILE, ECONOMICS_FILE)
# A clock-record interval whose wall advance exceeds its monotonic advance by more than this is a suspension.
SUSPENSION_GAP_SECONDS = 10
# A suspension bracketed by records closer than this (monotonic seconds) is placed by record; wider windows
# (reindexed runs: execution start, last heartbeat, finish) only bound it, and its position stays attributed.
RECORDED_PRECISION_SECONDS = 60
SKIP_DIRS = {"inputs", "sources", "cache", "staging", "raw", ".git"}
MAX_RECEIPT_BYTES = 1_000_000
MAX_SCANNED_FILES = 20000
WINDOW_SLACK_SECONDS = 2
COMPACTION_PREFIX = "[CONTEXT COMPACTION"
# A summary is counted as the deterministic fallback (the summarizer failed) when its `## Goal` section opens with
# the sentence Hermes's context compressor writes only into its local fallback (agent/context_compressor.py):
# "## Goal\nRecovered from a deterministic fallback ...". A model summary that merely mentions earlier fallbacks
# (e.g. under "## Errors & Fixes") is not one. It is a text match, not a signal from the harness: records and the
# UI label it "marker match".
FALLBACK_MARKER = "## Goal\nRecovered from a deterministic fallback"
FALLBACK_PATTERN = re.compile(r"^## Goal[ \t]*\r?\nRecovered from a deterministic fallback", re.MULTILINE)
FALLBACK_DETECTION = {"method": "marker_match", "marker": FALLBACK_MARKER,
                      "note": "a summary counts as the deterministic fallback when a line `## Goal` is followed by "
                              "`Recovered from a deterministic fallback` (Hermes's local fallback form)"}
ANALYSIS = re.compile(r"(?:run|\br)_analysis\.py")


def is_fallback(content):
    """Is this compaction summary Hermes's deterministic fallback (not a summary that mentions one)?"""
    return bool(FALLBACK_PATTERN.search(content or ""))
AGENT_DIR = re.compile(r"/agents/(agent_[0-9a-f]+)/")


def epoch(value):
    try:
        return datetime.fromisoformat(value).timestamp() if isinstance(value, str) and value else None
    except ValueError:
        return None


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def window(execution):
    """(start, finish) of the delivery in epoch seconds, from execution.json; None where unrecorded."""
    start = epoch(execution.get("started"))
    finish = epoch(execution.get("finished"))
    if finish is None and start is not None and _number(execution.get("wall_seconds")):
        finish = start + execution["wall_seconds"]
    return start, finish


# ---------------------------------------------------------------------------- clock records

def read_clock(folder):
    """Clock records of a run in recorded order, or None when the run has no clock.jsonl."""
    path = Path(folder) / CLOCK_FILE
    if not path.is_file() or path.is_symlink():
        return None
    records = []
    with path.open("rb") as stream:
        for raw in stream:
            try:
                value = json.loads(raw)
            except ValueError:
                continue
            if isinstance(value, dict) and _number(value.get("wall")) and _number(value.get("monotonic")):
                records.append(value)
    return records


def clock_windows(records):
    """Intervals between consecutive clock records where wall time advanced more than monotonic time by more
    than SUSPENSION_GAP_SECONDS: each brackets a suspension (or a wall-clock step) by record."""
    found = []
    for a, b in zip(records, records[1:], strict=False):
        wall, mono = b["wall"] - a["wall"], b["monotonic"] - a["monotonic"]
        if wall - mono > SUSPENSION_GAP_SECONDS:
            coarse = mono > RECORDED_PRECISION_SECONDS
            # G3: reindexed samples taken from the stream's own events sit on either side of one gap between
            # stamped events (`reindex_clock`), so no event lies inside the window: its position is fixed.
            bracketed = any(r.get("kind") == "event" and r.get("reindexed") for r in (a, b))
            found.append({"wall_from": a["wall"], "wall_to": b["wall"], "monotonic_from": a["monotonic"],
                          "monotonic_to": b["monotonic"], "seconds": round(wall - mono, 3),
                          "records": [a.get("n"), b.get("n")],
                          "sources": sorted({str(r.get("source") or CLOCK_FILE) for r in (a, b)}),
                          "precise": not coarse, "reindexed": bool(a.get("reindexed") and b.get("reindexed")),
                          "bracketed_by_events": bracketed})
    return found


def clock_summary(records, execution):
    """What the clock records say about the whole delivery, for the timeline."""
    if records is None:
        return None
    windows = clock_windows(records)
    recorded = round(sum(w["seconds"] for w in windows), 3)
    wall, mono = execution.get("wall_seconds"), execution.get("monotonic_seconds")
    total = round(wall - mono, 3) if _number(wall) and _number(mono) else None
    cadence = (execution.get("clock") or {}).get("cadence_seconds")
    return {"file": CLOCK_FILE, "records": len(records), "cadence_seconds": cadence,
            "reindexed": any(r.get("reindexed") for r in records), "suspended_seconds": recorded,
            "execution_suspended_seconds": total,
            "unrecorded_seconds": round(max(0.0, total - recorded), 3) if total is not None else None}


def stream_stamps(parsed):
    """(epoch seconds, stream line) of every event that carries its own timestamp (milliseconds since the epoch,
    as Hermes writes them), in stream order."""
    out = []
    for entry in parsed.get("events", []) if parsed else []:
        value = entry["event"].get("timestamp")
        if _number(value):
            out.append((value / 1000, entry["line"]))
    return out


def _event_samples(a, b, stamps):
    """Stream samples bracketing the suspension between two recorded samples a and b (G3), or [].

    Between a and b the wall clock advanced `held` seconds more than the monotonic clock. A suspended process
    emits no event, so the suspended time lies in gaps between stamped events. When exactly one such gap is at
    least `held` seconds long, the events on either side of it are paired with a monotonic time: before the gap
    wall and monotonic time advanced together from a, after it they advanced together up to b. This assumes the
    window's suspension is one contiguous host sleep (several shorter sleeps could share the window); when no
    gap or more than one gap could hold it, nothing is derived and the window stays as wide as a and b."""
    held = (b["wall"] - a["wall"]) - (b["monotonic"] - a["monotonic"])
    if held <= SUSPENSION_GAP_SECONDS:
        return []
    inside = [(wall, line) for wall, line in stamps if a["wall"] < wall < b["wall"]]
    points = [(a["wall"], None)] + inside + [(b["wall"], None)]
    gaps = [(q[0] - p[0], p, q) for p, q in zip(points, points[1:], strict=False)]
    candidates = [g for g in gaps if g[0] >= held]
    if len(candidates) != 1:
        return []
    _, before, after = candidates[0]
    basis = (f"the only gap between stamped events in [{a['source']}, {b['source']}] long enough to hold the "
             f"{round(held, 3)} s suspended there; one contiguous suspension assumed")
    samples = []
    if before[1] is not None:
        samples.append({"kind": "event", "wall": before[0], "monotonic": a["monotonic"] + (before[0] - a["wall"]),
                        "source": f"events.jsonl:{before[1]}", "side": "before_gap",
                        "derived": f"wall: the event's timestamp; monotonic: {a['source']} plus the wall advance "
                                   f"(no suspension before the gap). Gap: {basis}"})
    if after[1] is not None:
        samples.append({"kind": "event", "wall": after[0], "monotonic": b["monotonic"] - (b["wall"] - after[0]),
                        "source": f"events.jsonl:{after[1]}", "side": "after_gap",
                        "derived": f"wall: the event's timestamp; monotonic: {b['source']} minus the wall advance "
                                   f"(no suspension after the gap). Gap: {basis}"})
    return samples


def reindex_clock(execution, heartbeat, stamps=()):
    """Clock records from the samples an old run folder actually holds (G3): execution.json's start (both clocks
    at launch) and finish (wall and monotonic seconds), heartbeat.json's last sample, and, between two of those
    whose clocks diverged, the stream's own event timestamps on either side of the one gap that can hold the
    suspension (`_event_samples`). Nothing is interpolated; a run without both clocks in execution.json gets no
    clock records. Every record says `reindexed: true` and names its source."""
    start = epoch(execution.get("started"))
    if start is None or not (_number(execution.get("wall_seconds")) and _number(execution.get("monotonic_seconds"))):
        return []
    samples = [{"kind": "start", "wall": start, "monotonic": 0.0, "source": "execution.json:started"}]
    if isinstance(heartbeat, dict) and _number(heartbeat.get("elapsed_seconds")) and epoch(heartbeat.get("observed")):
        samples.append({"kind": "tick", "wall": epoch(heartbeat["observed"]),
                        "monotonic": float(heartbeat["elapsed_seconds"]), "stdout_bytes": heartbeat.get("stdout_bytes"),
                        "source": "heartbeat.json"})
    samples.append({"kind": "finish", "wall": start + execution["wall_seconds"],
                    "monotonic": float(execution["monotonic_seconds"]),
                    "source": "execution.json:wall_seconds,monotonic_seconds"})
    samples.sort(key=lambda r: r["monotonic"])
    derived = [s for a, b in zip(samples, samples[1:], strict=False) for s in _event_samples(a, b, list(stamps))]
    samples = sorted(samples + derived, key=lambda r: (r["monotonic"], r["wall"]))
    return [{"n": n, **{k: (round(v, 3) if k in ("wall", "monotonic") else v) for k, v in r.items()},
             "reindexed": True} for n, r in enumerate(samples)]


# ---------------------------------------------------------------------------- compactions

def state_db_compactions(path, execution):
    """Compaction summaries in a harness session database, bounded by the delivery window.

    Returns (items, reason): items is None when the database or its messages table is absent or unreadable."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        return None, "no session database in this run folder"
    start, finish = window(execution)
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error as error:
        return None, f"session database unreadable ({error})"
    try:
        columns = [r[1] for r in db.execute("PRAGMA table_info(messages)")]
        if "content" not in columns:
            return None, "the session database has no messages table"
        identity = "id" if "id" in columns else "rowid"
        session = next((c for c in ("session_id", "session") if c in columns), None)
        stamp = "timestamp" if "timestamp" in columns else None
        select = [identity, "content"] + ([stamp] if stamp else []) + ([session] if session else [])
        rows = db.execute(f"SELECT {','.join(select)} FROM messages WHERE content LIKE ? ORDER BY "
                          f"{(stamp + ',') if stamp else ''}rowid", (COMPACTION_PREFIX + "%",)).fetchall()
    except sqlite3.Error as error:
        return None, f"session database unreadable ({error})"
    finally:
        db.close()
    items = []
    for row in rows:
        value = dict(zip(select, row, strict=True))
        ts = value.get(stamp) if stamp else None
        if _number(ts) and ((start is not None and ts < start - 1) or (finish is not None and ts > finish + 1)):
            continue  # the snapshot database is cumulative per agent: other deliveries' rows
        content = value["content"] or ""
        data = content.encode("utf-8", errors="replace")
        items.append({"kind": "compaction", "message_id": value[identity], "timestamp": ts,
                      "session": value.get(session) if session else None,
                      "fallback": is_fallback(content), "fallback_detection": "marker_match",
                      "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return items, None


def transcript_compactions(path, execution):
    """Compaction summaries in Claude Code session transcripts (`projects/<cwd>/<session>.jsonl` snapshots),
    bounded by the delivery window: the entries Claude Code marks `isCompactSummary` after a compact boundary.
    Claude Code writes no fallback marker, so `fallback` is None (unavailable), never False.

    Returns (items, reason) like `state_db_compactions`; `message_id` is the entry's uuid (else file:line)."""
    path = Path(path)
    if not path.is_dir() or path.is_symlink():
        return None, "no session transcripts in this run folder"
    start, finish = window(execution)
    items = []
    for transcript in sorted(path.rglob("*.jsonl")):
        if transcript.is_symlink() or not transcript.is_file():
            continue
        with transcript.open("rb") as stream:
            for number, raw in enumerate(stream, 1):
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get("isCompactSummary") is not True:
                    continue
                ts = epoch(entry.get("timestamp"))
                if ts is not None and ((start is not None and ts < start - 1) or (finish is not None and ts > finish + 1)):
                    continue  # a resumed transcript holds earlier deliveries' summaries
                message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
                content = message.get("content")
                text = content if isinstance(content, str) else "\n".join(
                    c.get("text", "") for c in content or [] if isinstance(c, dict))
                data = text.encode("utf-8", errors="replace")
                items.append({"kind": "compaction",
                              "message_id": entry.get("uuid") or f"{transcript.relative_to(path).as_posix()}:{number}",
                              "timestamp": ts, "session": entry.get("sessionId"), "fallback": None,
                              "fallback_detection": None, "bytes": len(data),
                              "sha256": hashlib.sha256(data).hexdigest()})
    items.sort(key=lambda i: (i["timestamp"] is None, i["timestamp"] or 0))
    return items, None


def compaction_records(adapter, folder, execution, harness):
    """Header plus one record per compaction summary, or a header saying why they are unavailable."""
    header = {"kind": "header", "harness": harness, "recorded": now(),
              "window": {"started": execution.get("started"), "finished": execution.get("finished")}}
    source = getattr(adapter, "compaction_store", None) if adapter else None
    if not source:
        return [{**header, "available": False, "source": None,
                 "reason": "this harness's session state does not expose compaction summaries"}]
    reader = state_db_compactions if source.endswith(".db") else transcript_compactions
    items, reason = reader(Path(folder) / source, execution)
    if items is None:
        return [{**header, "available": False, "source": source, "reason": reason}]
    marked = reader is state_db_compactions
    return [{**header, "available": True, "source": source, "count": len(items),
             "fallbacks": sum(1 for i in items if i["fallback"]) if marked else None,
             "fallback_detection": FALLBACK_DETECTION if marked else None}] + items


def observed_events(lines, *, request, run, agent, harness, reindexed=False):
    """`compaction_observed` board event bodies, one per recorded summary (B10): its source row id and length as
    captured, the store it came from, and the fallback label (a marker match, or None where unavailable)."""
    header, items = lines[0], lines[1:]
    if not header.get("available"):
        return []
    return [{"request": request, "run": run, "agent": agent, "harness": harness, "source": header["source"],
             "source_row_id": item["message_id"], "bytes": item["bytes"], "sha256": item["sha256"],
             "timestamp": item.get("timestamp"), "session": item.get("session"), "fallback": item.get("fallback"),
             "fallback_detection": item.get("fallback_detection"), **({"reindexed": True} if reindexed else {})}
            for item in items]


def read_compactions(folder):
    """(header, items) from compactions.jsonl, or (None, None) when the run has none."""
    path = Path(folder) / COMPACTIONS_FILE
    if not path.is_file() or path.is_symlink():
        return None, None
    header, items = None, []
    with path.open("rb") as stream:
        for raw in stream:
            try:
                value = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(value, dict):
                continue
            if value.get("kind") == "header" and header is None:
                header = value
            elif value.get("kind") == "compaction":
                items.append(value)
    return header, items


# ---------------------------------------------------------------------------- analysis receipts

def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _relative(value, trial):
    """A checkout-relative path for a path a receipt recorded (host paths stay out of records)."""
    text = str(value or "")
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(Path(trial).resolve()).as_posix()
        except (ValueError, OSError):
            pass
        for marker in ("/trial/", "/workspace/"):
            if marker in text:
                tail = text.rsplit(marker, 1)[1]
                return tail if marker == "/trial/" else "workspace/" + tail
        return path.name
    return path.as_posix()


def _inside(trial, relative):
    """The file at a checkout-relative path, or None when it is outside the checkout or a symlink."""
    if not relative:
        return None
    base = Path(trial).resolve()
    candidate = base / relative
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(base) or candidate.is_symlink() or not resolved.is_file():
        return None
    return resolved


def _receipt_argument(command):
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    for i, word in enumerate(words):
        if word == "--receipt" and i + 1 < len(words):
            return words[i + 1]
        if word.startswith("--receipt="):
            return word.split("=", 1)[1]
    return None


def _printed(text):
    """`{"event": "analysis_executed", "receipt", "sha256"}` lines run_analysis.py printed into a tool output."""
    found = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if '"analysis_executed"' not in line:
            continue
        start = line.find("{")
        try:
            value = json.loads(line[start:]) if start >= 0 else None
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("event") == "analysis_executed":
            found.append(value)
    return found


def stream_calls(parsed, trial):
    """run_analysis.py calls in the stream: line, result line, exit code, receipt path named, sha256 printed."""
    calls = []
    for item in parsed.get("items", []):
        command = item.get("command") or ""
        if item.get("name") != "terminal" or not ANALYSIS.search(command):
            continue
        named = _receipt_argument(command)
        printed = _printed(item.get("aggregated_output") or item.get("output"))
        calls.append({"line": item.get("line"), "result_line": item.get("result_line"),
                      "exit_code": item.get("exit_code"), "receipt": _relative(named, trial) if named else None,
                      "printed": [{"receipt": _relative(p.get("receipt"), trial), "sha256": p.get("sha256")}
                                  for p in printed]})
    return calls


def _scan(trial):
    """JSON files under the checkout's question folders that look like run_analysis.py receipts."""
    questions = Path(trial) / "workspace" / "questions"
    found, scanned, truncated = [], 0, False
    if not questions.is_dir() or questions.is_symlink():
        return found, scanned, truncated
    stack = [questions]
    while stack:
        folder = stack.pop()
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    stack.append(entry)
                continue
            if entry.suffix != ".json":
                continue
            scanned += 1
            if scanned > MAX_SCANNED_FILES:
                return found, scanned, True
            try:
                if entry.stat().st_size <= MAX_RECEIPT_BYTES and b'"code_sha256"' in entry.read_bytes():
                    found.append(entry)
            except OSError:
                continue
    return found, scanned, truncated


def _receipt_shape(value):
    return (isinstance(value, dict) and value.get("version") == 1 and isinstance(value.get("argv"), list)
            and isinstance(value.get("code_sha256"), str) and isinstance(value.get("outputs"), list)
            and isinstance(value.get("started"), str))


def _now_state(trial, relative, expected):
    if expected is None:
        return None
    path = _inside(trial, relative)
    if path is None:
        return "missing"
    try:
        return "unchanged" if file_hash(path) == expected else "changed"
    except OSError:
        return "missing"


def index_receipts(trial, folder, execution, parsed, *, agent=None, run=None):
    """The receipts.json record for one delivery (see the module docstring). Copies receipt bytes into
    `<folder>/receipts/<sha256>.json`; never modifies the checkout."""
    trial, folder = Path(trial), Path(folder)
    start, finish = window(execution)
    calls = stream_calls(parsed, trial)
    named = {}
    for call in calls:
        for path in [call["receipt"]] + [p["receipt"] for p in call["printed"]]:
            if path:
                named.setdefault(path, call)
    candidates = {}
    for relative in named:
        path = _inside(trial, relative)
        if path is not None:
            candidates[path] = "stream"
    scanned, scan_count, truncated = _scan(trial) if trial.is_dir() else ([], 0, False)
    for path in scanned:
        candidates.setdefault(path.resolve(), "scan")
    receipts, skipped = [], {"outside_window": 0, "foreign_checkout": 0, "not_a_receipt": 0, "unbounded": 0}
    for path, found_by in sorted(candidates.items(), key=lambda kv: str(kv[0])):
        try:
            data = path.read_bytes()
            value = json.loads(data)
        except (OSError, ValueError):
            skipped["not_a_receipt"] += 1
            continue
        if not _receipt_shape(value):
            skipped["not_a_receipt"] += 1
            continue
        began, ended = epoch(value.get("started")), epoch(value.get("finished"))
        if start is None or finish is None or began is None:
            skipped["unbounded"] += 1
            continue
        if began < start - WINDOW_SLACK_SECONDS or began > finish + WINDOW_SLACK_SECONDS or (
                ended is not None and ended > finish + WINDOW_SLACK_SECONDS):
            skipped["outside_window"] += 1
            continue
        owner = AGENT_DIR.search(str(value.get("cwd") or "") + "/")
        if agent and owner and owner.group(1) != agent:
            skipped["foreign_checkout"] += 1  # inherited by a fork, or written in another participant's checkout
            continue
        sha = _sha(data)
        copy = folder / RECEIPT_DIR / f"{sha}.json"
        if not copy.exists():
            copy.parent.mkdir(parents=True, exist_ok=True)
            temp = copy.with_suffix(".tmp")
            temp.write_bytes(data)
            temp.replace(copy)
        relative = path.relative_to(trial.resolve()).as_posix()
        call = named.get(relative)
        printed = [p["sha256"] for c in calls for p in c["printed"] if p["receipt"] == relative and p.get("sha256")]
        producer = _relative(value.get("producer"), trial)
        outputs = []
        for item in value["outputs"]:
            if not isinstance(item, dict):
                continue
            output = _relative(item.get("path"), trial)
            outputs.append({"path": output, "sha256": item.get("sha256"), "written": item.get("written"),
                            "now": _now_state(trial, output, item.get("sha256"))})
        sidecars = {}
        for suffix in ("stdout", "stderr"):
            side = path.with_suffix(path.suffix + "." + suffix)
            if side.is_file() and not side.is_symlink():
                sidecars[suffix] = {"bytes": side.stat().st_size, "sha256": file_hash(side)}
        complete, code = value.get("complete"), value.get("exit_code")
        outcome = "pass" if complete is True else "fail" if complete is False or (_number(code) and code != 0) else "unknown"
        receipts.append({
            "path": relative, "sha256": sha, "bytes": len(data), "copy": f"{RECEIPT_DIR}/{sha}.json", "found_by": found_by,
            "started": value.get("started"), "finished": value.get("finished"), "exit_code": code,
            "complete": complete, "code_unchanged": value.get("code_unchanged"), "outcome": outcome,
            "producer": producer, "code_sha256": value["code_sha256"], "argv": [str(a) for a in value["argv"]][:8],
            "outputs": outputs, "sidecars": sidecars, "error": value.get("error"),
            "line": call["line"] if call else None, "result_line": call["result_line"] if call else None,
            "stream_exit_code": call["exit_code"] if call else None,
            "verified": {"stream_sha256": ("matches" if sha in printed else "differs") if printed else None,
                         "producer_now": _now_state(trial, producer, value["code_sha256"]),
                         "outputs_now": sorted({o["now"] for o in outputs if o["now"]})}})
    matched = {r["line"] for r in receipts if r["line"] is not None}
    receipts.sort(key=lambda r: (r["started"] or "", r["path"]))
    return {"version": 1, "run": run, "agent": agent, "indexed": now(),
            "window": {"started": execution.get("started"), "finished": execution.get("finished"),
                       "slack_seconds": WINDOW_SLACK_SECONDS},
            "receipts": receipts,
            "unreceipted_calls": [{"line": c["line"], "exit_code": c["exit_code"], "receipt": c["receipt"]}
                                  for c in calls if c["line"] not in matched],
            "scanned": {"files": scan_count, "truncated": truncated, "named_in_stream": len(named),
                        "skipped": skipped},
            "counts": {"receipts": len(receipts), "pass": sum(r["outcome"] == "pass" for r in receipts),
                       "fail": sum(r["outcome"] == "fail" for r in receipts)}}


def read_receipts(folder):
    path = Path(folder) / RECEIPTS_FILE
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = read_json(path)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) and isinstance(value.get("receipts"), list) else None


# ---------------------------------------------------------------------------- writing records

def _write_lines(path, lines):
    """Create a JSONL record; never overwrite one that exists."""
    with Path(path).open("x", encoding="utf-8") as stream:
        for line in lines:
            stream.write(json.dumps(line, separators=(",", ":"), allow_nan=False) + "\n")


def _write_once(path, value):
    if Path(path).exists():
        return False
    write_json(path, value)
    return True


def record_delivery(board, request_id, run_id, agent, adapter, folder, trial, execution, parsed, *, harness=None):
    """Capture-time records after one delivery: compactions.jsonl with one `compaction_observed` board event per
    summary, receipts.json with a `receipts_indexed` board event, and turn_economics.json. Each part is best
    effort and reported; a failure here never fails the delivery."""
    from daw.commons import economics
    folder = Path(folder)
    harness = harness or getattr(adapter, "name", None)
    done, problems = {}, {}
    try:
        if not (folder / COMPACTIONS_FILE).exists():
            lines = compaction_records(adapter, folder, execution, harness)
            _write_lines(folder / COMPACTIONS_FILE, lines)
            done["compactions"] = lines[0].get("count") if lines[0]["available"] else "unavailable"
            observed = observed_events(lines, request=request_id, run=run_id, agent=agent["id"], harness=harness)
            if observed:
                with board.writer(), board.db:
                    for body in observed:
                        board.event("compaction_observed", body)
    except (OSError, ValueError, sqlite3.Error) as error:
        problems["compactions"] = str(error)
    try:
        if not (folder / RECEIPTS_FILE).exists():
            index = index_receipts(trial, folder, execution, parsed, agent=agent["id"], run=run_id)
            _write_once(folder / RECEIPTS_FILE, index)
            done["receipts"] = index["counts"]
            with board.writer(), board.db:
                board.event("receipts_indexed", {"request": request_id, "run": run_id, "agent": agent["id"],
                                                 **index["counts"], "file_sha256": file_hash(folder / RECEIPTS_FILE),
                                                 "unreceipted_calls": len(index["unreceipted_calls"])})
    except (OSError, ValueError, DawError, sqlite3.Error) as error:
        problems["receipts"] = getattr(error, "reason", None) or str(error)
    try:
        if not (folder / ECONOMICS_FILE).exists():
            record = economics.turn_economics(folder, parsed, execution, harness=harness, run=run_id,
                                              agent=agent["id"], config=agent.get("config"), trial=trial)
            _write_once(folder / ECONOMICS_FILE, record)
            done["turn_economics"] = True
    except (OSError, ValueError, DawError, sqlite3.Error) as error:
        problems["turn_economics"] = getattr(error, "reason", None) or str(error)
    if problems:
        write_json(folder / "records-error.json", {"observed": now(), "problems": problems})
    return {"recorded": done, "problems": problems}


def reindex_run(board, actor, run):
    """`bio commons runs reindex RUN`: build the records an old run lacks from what exists (operator only)."""
    from daw import harness as harnesses
    from daw.commons.permissions import require
    require(board, board.agent(actor), "recover")
    attempt = board.one("SELECT * FROM attempt WHERE id=?", (run,))
    if not attempt:
        raise DawError("unknown_run", run)
    if attempt["state"] == "running":
        raise DawError("run_in_progress", "records are written by the runtime when the delivery ends")
    folder = (board.root / attempt["path"]).resolve()
    if not folder.is_relative_to((board.root / "runs").resolve()) or not folder.is_dir():
        raise DawError("unsafe_run_path", run)
    agent = board.agent(attempt["target"])
    try:
        adapter = harnesses.for_agent(agent)
    except DawError:
        adapter = None
    execution = read_json(folder / "execution.json") if (folder / "execution.json").is_file() else {}
    parsed = adapter.parse(folder / "events.jsonl") if adapter else {"items": [], "events": []}
    harness = getattr(adapter, "name", None)
    written, kept, unavailable = [], [], {}
    if (folder / CLOCK_FILE).exists():
        kept.append(CLOCK_FILE)
    else:
        heartbeat = None
        if (folder / "heartbeat.json").is_file():
            try:
                heartbeat = read_json(folder / "heartbeat.json")
            except ValueError:
                heartbeat = None
        records = reindex_clock(execution, heartbeat, stream_stamps(parsed))
        if records:
            _write_lines(folder / CLOCK_FILE, records)
            written.append(CLOCK_FILE)
        else:
            unavailable[CLOCK_FILE] = "execution.json does not record both clocks"
    if (folder / COMPACTIONS_FILE).exists():
        kept.append(COMPACTIONS_FILE)
    else:
        lines = compaction_records(adapter, folder, execution, harness)
        lines[0]["reindexed"] = True
        _write_lines(folder / COMPACTIONS_FILE, lines)
        written.append(COMPACTIONS_FILE)
        if not lines[0]["available"]:
            unavailable[COMPACTIONS_FILE] = lines[0]["reason"]
        observed = observed_events(lines, request=attempt["request"], run=run, agent=agent["id"], harness=harness,
                                   reindexed=True)
        if observed:
            with board.writer(), board.db:
                for body in observed:
                    board.event("compaction_observed", {**body, "actor": actor})
    counts = None
    trial = board.trial(agent) if agent.get("trial") else None
    start, finish = window(execution)
    if (folder / RECEIPTS_FILE).exists():
        kept.append(RECEIPTS_FILE)
    elif trial is None or not Path(trial).is_dir():
        unavailable[RECEIPTS_FILE] = "the participant's checkout is not present"  # not written: unknown, not zero
    elif start is None or finish is None:
        unavailable[RECEIPTS_FILE] = "execution.json does not bound the delivery"
    else:
        index = index_receipts(trial, folder, execution, parsed, agent=agent["id"], run=run)
        index["reindexed"] = {"by": actor, "note": "indexed after the delivery from the checkout as it is now"}
        write_json(folder / RECEIPTS_FILE, index)
        written.append(RECEIPTS_FILE)
        counts = index["counts"]
        with board.writer(), board.db:
            board.event("receipts_indexed", {"request": attempt["request"], "run": run, "agent": agent["id"], **counts,
                                             "file_sha256": file_hash(folder / RECEIPTS_FILE), "reindexed": True,
                                             "actor": actor, "unreceipted_calls": len(index["unreceipted_calls"])})
    if (folder / ECONOMICS_FILE).exists():
        kept.append(ECONOMICS_FILE)
    else:
        from daw.commons import economics
        record = economics.turn_economics(folder, parsed, execution, harness=harness, run=run, agent=agent["id"],
                                          config=agent.get("config"), trial=None)
        record["reindexed"] = {"by": actor, "note": "computed after the delivery from the run folder; the skill text "
                                                    "staged for the turn was not recorded"}
        write_json(folder / ECONOMICS_FILE, record)
        written.append(ECONOMICS_FILE)
    return {"run": run, "written": written, "kept": kept, "unavailable": unavailable, "receipts": counts}

