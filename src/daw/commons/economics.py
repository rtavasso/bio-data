"""Turn economics (spec v3 V13): where one delivery's context and time went, and what useful data cost.

`turn_economics(...)` is the `turn_economics.json` record the runtime writes into each run folder at capture
time (`daw.commons.records.record_delivery`; `bio commons runs reindex` writes it for older runs, marked
`reindexed`). It reads the run folder only:

- `tokens`: provider telemetry (input, cached input, output) as the harness reported it, None when unreported.
  Harnesses disagree on `input_tokens`: Codex and Claude Code (as daw records it) count cached input inside it,
  Hermes does not. `tokens_normalised` gives uncached input (input minus cached where the harness includes it),
  cached input and output, so sums across harnesses add like with like; None for a harness of unknown semantics.
- `context`: input context per model call, or per turn where the harness reports only turn totals (`unit`),
  from `daw.commons.hygiene.context_per_call`; `model_calls` where the stream marks model calls (Claude Code's
  assistant messages), else None.
- `composition`: bytes of model-facing content by source. From the session database when it classifies its
  messages (roles and tool names, Hermes): system prompt, skills (skill tool results), tool outputs, compaction
  summaries and the conversation (prompts and replies). Otherwise from the stream: tool outputs as the stream
  carries them (Hermes caps them upstream at 5000 characters, so these are lower bounds; a redacted fixture stream
  keeps each output's original length), skills (skill views and SKILL.md reads), summaries from compactions.jsonl
  and the delivery prompt from prompt.txt; the system prompt is in no stream, so it is None. `shares` are byte
  shares, given only when every component was measured: a proxy for context composition, not token counts.
- `compactions`: stream markers, recorded summaries, fallbacks (a marker match, `daw.commons.records`).
- `time`: minutes waiting on tools (the union of tool-call intervals between stamped events) and the rest of the
  stream's span (model generation and harness time between tool calls). None when the stream carries no
  timestamps, or when a host suspension lies inside the span (it would be counted as one or the other).
- `orientation`: help calls and re-orientation calls (inbox, forum search, overview, LABBOOK reads, skill reads,
  status checks), by kind.
- `ceremony_tail_minutes`: minutes after the last successful analysis (`daw.commons.runmetrics`).
- `skills`: reads per skill in this turn, and the sha256 of each skill's text staged in the checkout at capture
  (`version` digests them; None when not recorded, as for reindexed runs).

`criteria(runs, data)` aggregates records for a dashboard group (per harness, per skill version) and divides tokens
by useful data: registered artifacts, claims with a verified pointer, frontier items later promoted. Anything that
cannot be computed is None, never zero.
"""
import hashlib
import json
import re
import sqlite3
import statistics
from pathlib import Path

from daw.commons import hygiene
from daw.skill_budget import BUDGET_BYTES, skill_digest, skill_dirs, skill_sizes
from daw.util import now, read_json

FILE = "turn_economics.json"
VERSION = 1
COMPONENTS = ("system_prompt", "delivery_prompt", "skills", "tool_outputs", "summaries", "conversation")
REDACTED = re.compile(r"\[redacted (\d+) bytes sha256:[0-9a-f]{64}\]")
SKILL_PATH = re.compile(r"(?:^|[/\s'\"])(?:\.agents/)?skills/([A-Za-z0-9][A-Za-z0-9_.-]*)/(?:SKILL\.md|references/)")
SKILL_TOOLS = {"skill_view", "Skill"}
REORIENTATION = (("inbox", re.compile(r"\bcommunity\s+inbox\b")),
                 ("forum_search", re.compile(r"\b(community\s+search|bio\s+search)\b")),
                 ("overview", re.compile(r"\bcommunity\s+overview\b")),
                 ("status", re.compile(r"\b(git\s+status|bio\s+work\s+status|bio\s+status)\b")))
HELP = re.compile(r"(^|\s)(--help|-h)(\s|$)")
LABBOOK = re.compile(r"LABBOOK\.md")
# Does this harness's recorded `input_tokens` already contain `cached_input_tokens`? Codex reports OpenAI usage
# (input includes cached); daw's Claude Code adapter adds cache creation and reads into input; Hermes reports
# uncached input with cache reads separate. Harnesses not listed (mcp: whatever the configured agent reports)
# have unknown semantics and are not normalised.
INPUT_INCLUDES_CACHED = {"codex": True, "claude": True, "hermes": False}
LIMITATIONS = [
    "Composition is bytes of model-facing content, not provider tokens; shares are given only when every source was "
    "measured (the system prompt is in the session database, never in a stream).",
    "Hermes caps tool outputs in its stream at 5000 characters: stream-measured tool output bytes are lower bounds.",
    "Generation versus tool wait is measured on the stream's own timestamps; it is unavailable for streams without "
    "timestamps (Claude Code, Codex) and for runs with a host suspension inside the stream.",
    "Cost per useful datum divides the group's reported tokens (uncached input plus output, normalised per harness: "
    "Codex and Claude Code count cached input inside input_tokens, Hermes does not) by registered artifacts, claims "
    "with a verified pointer, and frontier items later promoted; None when tokens are incomplete, a harness's input "
    "semantics are unknown, or the count is 0.",
]


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _bytes(value):
    if value is None:
        return 0
    text = value if isinstance(value, str) else json.dumps(value)
    found = REDACTED.search(text)
    if found and len(text) < 400:
        return int(found.group(1))  # a redacted fixture stream keeps the original output's length
    return len(text.encode("utf-8", errors="replace"))


def skill_read(item):
    """The skill a tool call read (a skill tool, or a SKILL.md/references path in a read or command), or None."""
    tool_input = item.get("input") if isinstance(item.get("input"), dict) else {}
    if item.get("name") in SKILL_TOOLS or item.get("native_name") in SKILL_TOOLS:
        value = tool_input.get("name") or tool_input.get("skill") or tool_input.get("command")
        return str(value) if value else "(unnamed)"
    for text in (tool_input.get("path"), tool_input.get("file_path"), item.get("command")):
        found = SKILL_PATH.search(str(text or ""))
        if found:
            return found.group(1)
    return None


def _orientation(items):
    kinds = dict.fromkeys(["inbox", "forum_search", "overview", "status", "labbook_reads", "skill_reads"], 0)
    helps = 0
    for item in items:
        command = item.get("command") or ""
        if item.get("name") == "terminal":
            if HELP.search(command):
                helps += 1
            for kind, pattern in REORIENTATION:
                if pattern.search(command):
                    kinds[kind] += 1
                    break
        tool_input = item.get("input") if isinstance(item.get("input"), dict) else {}
        if LABBOOK.search(str(tool_input.get("path") or "")) or (
                item.get("name") == "terminal" and LABBOOK.search(command) and re.search(r"\b(cat|sed|head|tail|less)\b", command)):
            kinds["labbook_reads"] += 1
        if skill_read(item):
            kinds["skill_reads"] += 1
    return {"help_calls": helps, "reorientation_calls": sum(kinds.values()), "by_kind": kinds}


def _stream_composition(folder, parsed, compactions):
    out = dict.fromkeys(COMPONENTS)
    skills = tools = 0
    for item in parsed["items"]:
        if item.get("type") == "agent_message":
            continue
        size = _bytes(item.get("aggregated_output"))
        if skill_read(item):
            skills += size
        else:
            tools += size
    out.update(skills=skills, tool_outputs=tools)
    prompt = Path(folder) / "prompt.txt"
    out["delivery_prompt"] = prompt.stat().st_size if prompt.is_file() else None
    header, items = compactions
    out["summaries"] = sum(i.get("bytes") or 0 for i in items) if header and header.get("available") else None
    return out


def _database_composition(folder, execution, parsed):
    """Bytes by source from the session database, or None when it does not classify messages by role."""
    from daw.commons.records import COMPACTION_PREFIX, window
    path = Path(folder) / "agent-state" / "state.db"
    if not path.is_file() or path.is_symlink():
        return None
    start, finish = window(execution)
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        columns = [r[1] for r in db.execute("PRAGMA table_info(messages)")]
        if not {"role", "content"} <= set(columns):
            return None
        tool = "tool_name" if "tool_name" in columns else "NULL"
        stamp = "timestamp" if "timestamp" in columns else "NULL"
        rows = db.execute(f"SELECT role,{tool},content,{stamp} FROM messages").fetchall()
        sessions = [s for s in parsed.get("thread_ids") or [] if isinstance(s, str)]
        system = None
        session_columns = [r[1] for r in db.execute("PRAGMA table_info(sessions)")]
        if "system_prompt" in session_columns and sessions:
            prompts = [r[0] for r in db.execute(
                f"SELECT system_prompt FROM sessions WHERE id IN ({','.join('?' * len(set(sessions)))})",
                sorted(set(sessions)))]
            if prompts and all(p is not None for p in prompts):
                system = sum(len(p.encode("utf-8", errors="replace")) for p in prompts)
    except sqlite3.Error:
        return None
    finally:
        db.close()
    out = dict.fromkeys(COMPONENTS)
    out.update(system_prompt=system, skills=0, tool_outputs=0, summaries=0, conversation=0)
    for role, tool_name, content, ts in rows:
        if _number(ts) and ((start is not None and ts < start - 1) or (finish is not None and ts > finish + 1)):
            continue  # the snapshot database is cumulative per agent
        size = len((content or "").encode("utf-8", errors="replace"))
        if (content or "").startswith(COMPACTION_PREFIX):
            out["summaries"] += size
        elif role == "system":
            out["system_prompt"] = (out["system_prompt"] or 0) + size
        elif role == "tool":
            out["skills" if str(tool_name or "") in SKILL_TOOLS else "tool_outputs"] += size
        else:
            out["conversation"] += size
    return out


def composition(folder, execution, parsed, compactions):
    measured = _database_composition(folder, execution, parsed)
    basis = "session_database" if measured is not None else "stream"
    measured = measured if measured is not None else _stream_composition(folder, parsed, compactions)
    used = {k: v for k, v in measured.items() if v is not None}
    expected = (("system_prompt", "skills", "tool_outputs", "summaries", "conversation") if basis == "session_database"
                else COMPONENTS)
    complete = all(measured.get(k) is not None for k in expected)
    total = sum(used.values())
    return {"basis": basis, "bytes": measured, "complete": complete,
            "shares": {k: round(v / total, 4) for k, v in used.items()} if complete and total else None}


def _time(parsed, execution, suspended):
    stamps = {e["line"]: e["event"]["timestamp"] / 1000 for e in parsed.get("events", [])
              if _number(e["event"].get("timestamp"))}
    if len(stamps) < 2:
        return {"tool_wait_minutes": None, "generation_minutes": None,
                "basis": "the stream carries no event timestamps"}
    if suspended:
        return {"tool_wait_minutes": None, "generation_minutes": None,
                "basis": f"a host suspension of {suspended} s lies inside the stream's span"}
    intervals = sorted((stamps[i["line"]], stamps[i["result_line"]]) for i in parsed["items"]
                       if i.get("line") in stamps and i.get("result_line") in stamps
                       and stamps[i["result_line"]] >= stamps[i["line"]])
    wait, current = 0.0, None
    for low, high in intervals:
        if current and low <= current[1]:
            current[1] = max(current[1], high)
            continue
        if current:
            wait += current[1] - current[0]
        current = [low, high]
    if current:
        wait += current[1] - current[0]
    span = max(stamps.values()) - min(stamps.values())
    return {"tool_wait_minutes": round(wait / 60, 2), "generation_minutes": round(max(0.0, span - wait) / 60, 2),
            "stream_span_minutes": round(span / 60, 2),
            "basis": "stream timestamps: union of tool-call intervals versus the rest of the span"}


def normalised_tokens(tokens, harness):
    """{uncached_input_tokens, cached_input_tokens, output_tokens, input_includes_cached} from a run's recorded
    tokens, or None when tokens are unreported, the harness's input semantics are unknown, or the cached count
    is needed and missing. Uncached input is what cost and cross-harness sums should add."""
    if not tokens or harness not in INPUT_INCLUDES_CACHED:
        return None
    includes, cached = INPUT_INCLUDES_CACHED[harness], tokens.get("cached_input_tokens")
    if includes and cached is None:
        return None
    uncached = tokens["input_tokens"] - cached if includes else tokens["input_tokens"]
    if uncached < 0:
        return None
    return {"uncached_input_tokens": uncached, "cached_input_tokens": cached, "output_tokens": tokens["output_tokens"],
            "input_includes_cached": includes}


def skill_versions(trial):
    """{skill: sha256 of its text} staged in a checkout's .agents/skills, or None when there are none."""
    if trial is None:
        return None
    versions = {p.name: skill_digest(p) for p in skill_dirs(Path(trial) / ".agents" / "skills")}
    return versions or None


def turn_economics(folder, parsed, execution, *, harness, run=None, agent=None, config=None, trial=None):
    """The turn_economics.json record of one delivery (see the module docstring)."""
    from daw.commons import metrics
    from daw.commons.records import read_compactions
    from daw.commons.runmetrics import compactions_reported, run_metrics
    folder = Path(folder)
    reported = compactions_reported(harness, config if isinstance(config, dict) else None)
    behaviour = run_metrics(folder, parsed, compactions_reported=reported)
    tokens, note = metrics.token_usage(parsed)
    compactions = read_compactions(folder)
    header, items = compactions
    tools = [i for i in parsed["items"] if i.get("type") != "agent_message"]
    reads = {}
    for item in tools:
        name = skill_read(item)
        if name:
            reads[name] = reads.get(name, 0) + 1
    versions = skill_versions(trial)
    calls = None
    if harness == "claude":
        ids = {(e["event"].get("message") or {}).get("id") for e in parsed.get("events", [])
               if e["event"].get("type") == "assistant" and isinstance(e["event"].get("message"), dict)}
        calls = len(ids - {None}) or None
    stream = (folder / "events.jsonl").is_file()
    return {"version": VERSION, "kind": "turn_economics", "run": run, "agent": agent, "harness": harness,
            "recorded": now(), "tokens": tokens, "tokens_note": note,
            "tokens_normalised": normalised_tokens(tokens, harness),
            "context": hygiene.context_per_call(folder / "events.jsonl"), "model_calls": calls,
            "composition": composition(folder, execution, parsed, compactions),
            "compactions": {"stream_markers": behaviour["compactions"],
                            "summaries": header.get("count") if header and header.get("available") else None,
                            "fallbacks": header.get("fallbacks") if header and header.get("available") else None,
                            "fallback_detection": "marker_match" if header and header.get("fallback_detection") else None},
            "time": {"monotonic_minutes": round(behaviour["monotonic_seconds"] / 60, 2)
                     if behaviour["monotonic_seconds"] is not None else None,
                     "suspended_minutes": round(behaviour["suspended_seconds"] / 60, 2)
                     if behaviour["suspended_seconds"] is not None else None,
                     **_time(parsed, execution, behaviour["suspended_seconds"])},
            "orientation": _orientation(tools) if stream else None,
            "ceremony_tail_minutes": behaviour["minutes_after_last_successful_analysis"],
            "skills": {"reads": reads if stream else None, "reads_total": sum(reads.values()) if stream else None,
                       "versions": versions,
                       "version": hashlib.sha256(json.dumps(versions, sort_keys=True).encode()).hexdigest()[:12]
                       if versions else None},
            "limitations": LIMITATIONS}


def read(folder):
    """The run's turn_economics.json, or None when the run has none."""
    path = Path(folder) / FILE
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = read_json(path)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) and value.get("kind") == "turn_economics" else None


# ---------------------------------------------------------------- group aggregates (dashboard)

def _sum(values):
    known = [v for v in values if v is not None]
    return round(sum(known), 2) if known else None


def _per(numerator, denominator, digits=1):
    return round(numerator / denominator, digits) if numerator is not None and denominator else None


def criteria(runs, data=None):
    """Turn economics over a group of runs (load_runs rows) and, given `data` (counts of registered artifacts,
    claims with a verified pointer and frontier items later promoted in the group's scope), tokens per datum."""
    records = [r["metrics"].get("turn_economics") for r in runs]
    recorded = [e for e in records if e]
    contexts = [e["context"] for e in recorded if e.get("context")]
    units = sorted({c["unit"] for c in contexts})
    calls = sum(c["records"] for c in contexts)
    complete = [e["composition"] for e in recorded if (e.get("composition") or {}).get("complete")]
    composed = {k: sum(c["bytes"].get(k) or 0 for c in complete) for k in COMPONENTS}
    whole = sum(composed.values())
    measured = {k: _sum((e.get("composition") or {}).get("bytes", {}).get(k) for e in recorded) for k in COMPONENTS}
    times = [e["time"] for e in recorded if (e.get("time") or {}).get("tool_wait_minutes") is not None]
    oriented = [e["orientation"] for e in recorded if e.get("orientation")]
    tails = [e["ceremony_tail_minutes"] for e in recorded if e.get("ceremony_tail_minutes") is not None]
    reads, read_runs = {}, [e for e in recorded if (e.get("skills") or {}).get("reads") is not None]
    for e in read_runs:
        for name, count in e["skills"]["reads"].items():
            reads[name] = reads.get(name, 0) + count
    # Tokens from the runs' telemetry (the metrics projection), only when every run in the group reported them,
    # normalised per harness to uncached input plus output: Codex's input_tokens include cached tokens and
    # Hermes's do not, so a raw sum overstated Codex ~20x beside Hermes.
    token_runs = [r["metrics"].get("tokens") for r in runs]
    normal = [normalised_tokens(t, r.get("harness") or (r["metrics"].get("turn_economics") or {}).get("harness"))
              for t, r in zip(token_runs, runs, strict=True)]
    complete_tokens = bool(runs) and all(normal)
    tokens = sum(n["uncached_input_tokens"] + n["output_tokens"] for n in normal) if complete_tokens else None
    data = data or {}
    return {
        "runs": len(runs), "recorded_runs": len(recorded), "unrecorded_runs": len(runs) - len(recorded),
        "reindexed_runs": sum(1 for e in recorded if e.get("reindexed")),
        "context": {"unit": units[0] if len(units) == 1 else ("mixed" if units else None), "records": calls,
                    "mean_input_tokens": round(sum(c["mean_input_tokens"] * c["records"] for c in contexts) / calls, 1)
                    if calls else None,
                    "max_input_tokens": max(c["max_input_tokens"] for c in contexts) if contexts else None,
                    "model_calls": _sum(e.get("model_calls") for e in recorded)},
        "composition": {"bytes_measured": measured, "complete_runs": len(complete),
                        "shares": {k: round(v / whole, 4) for k, v in composed.items()} if whole else None},
        "compactions": {"stream_markers": _sum((e.get("compactions") or {}).get("stream_markers") for e in recorded),
                        "summaries": _sum((e.get("compactions") or {}).get("summaries") for e in recorded),
                        "fallbacks": _sum((e.get("compactions") or {}).get("fallbacks") for e in recorded),
                        "fallback_detection": "marker_match"},
        "time": {"runs": len(times), "generation_minutes": _sum(t["generation_minutes"] for t in times),
                 "tool_wait_minutes": _sum(t["tool_wait_minutes"] for t in times),
                 "tool_wait_share": _per(_sum(t["tool_wait_minutes"] for t in times),
                                         _sum(t["tool_wait_minutes"] + t["generation_minutes"] for t in times), 3)},
        "orientation": {"runs": len(oriented),
                        "help_calls_per_turn": _per(sum(o["help_calls"] for o in oriented), len(oriented), 2),
                        "reorientation_calls_per_turn": _per(sum(o["reorientation_calls"] for o in oriented),
                                                             len(oriented), 2),
                        "by_kind": {k: sum(o["by_kind"].get(k, 0) for o in oriented)
                                    for k in (oriented[0]["by_kind"] if oriented else {})}},
        "ceremony_tail_minutes": {"runs": len(tails), "median": round(statistics.median(tails), 1) if tails else None},
        "skill_reads": {"runs": len(read_runs), "total": sum(reads.values()) if read_runs else None,
                        "per_turn": {k: _per(v, len(read_runs), 2) for k, v in sorted(reads.items())}},
        "tokens": tokens, "tokens_reported_runs": sum(1 for t in token_runs if t),
        "tokens_normalised_runs": sum(1 for n in normal if n),
        "token_fields": {k: sum(n[k] for n in normal) if complete_tokens else None
                         for k in ("uncached_input_tokens", "cached_input_tokens", "output_tokens")},
        "tokens_meaning": "uncached input plus output tokens, normalised per harness (cached input excluded)",
        "useful_data": {k: data.get(k) for k in ("registered_artifacts", "verified_claims", "promoted_frontier_items")},
        "tokens_per": {"registered_artifact": _per(tokens, data.get("registered_artifacts"), 0),
                       "verified_claim": _per(tokens, data.get("verified_claims"), 0),
                       "promoted_frontier_item": _per(tokens, data.get("promoted_frontier_items"), 0)},
    }


def skill_version_key(run):
    economics = run["metrics"].get("turn_economics") or {}
    return (economics.get("skills") or {}).get("version") or "unrecorded"


def skill_table(runs, root=None):
    """Each platform skill's text size beside its budget, and how often a turn reads it (over runs whose
    reads were recorded). Skills read but not present here are listed with size None."""
    sizes = skill_sizes(root) if root is not None else skill_sizes()
    read_runs = [r["metrics"]["turn_economics"] for r in runs if ((r["metrics"].get("turn_economics") or {})
                                                                  .get("skills") or {}).get("reads") is not None]
    reads = {}
    for e in read_runs:
        for name, count in e["skills"]["reads"].items():
            reads[name] = reads.get(name, 0) + count
    names = sorted(set(sizes) | set(reads) | set(BUDGET_BYTES))
    return {"runs": len(read_runs),
            "items": [{"skill": name, "bytes": (sizes.get(name) or {}).get("bytes"), "budget": BUDGET_BYTES.get(name),
                       "reads": reads.get(name, 0) if read_runs else None,
                       "reads_per_turn": _per(reads.get(name, 0), len(read_runs), 2)} for name in names]}
