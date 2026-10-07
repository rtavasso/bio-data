"""Per-delivery behavioural metrics from a run folder (M9.1).

Shared by the community audit report and the commons web app. Wall time
includes host sleep; monotonic time does not. Counts are behaviour, not
scientific value.
"""
import re
from pathlib import Path

from daw.community import PROVIDER_CITATION
from daw.util import read_json

PLUMBING = re.compile(r"(retriev|acquire|fetch|download|get_source|register|publish|verify|validat|package|check_|readback|"
                      r"inspect_|research_io|community_|handoff|export|resume_)", re.IGNORECASE)
VERIFY = re.compile(r"(verify|readback|validate_publication|check_publication)", re.IGNORECASE)
INSPECT = re.compile(r"(inspect|peek|probe|extract_|dump_|locate_|inventory|survey_)", re.IGNORECASE)
SUSPENSION_FLOOR_SECONDS = 60


def compaction_summaries(folder, execution):
    """Compaction handoffs written during this delivery, and how many were the deterministic
    placeholder (the summarizer failed). The snapshot database is cumulative per agent, so rows are
    bounded by the delivery's start and finish timestamps."""
    import sqlite3
    from datetime import datetime
    db = folder / "agent-state" / "state.db"
    if not db.exists():
        return None, None
    bounds = []
    for key in ("started", "finished"):
        value = execution.get(key)
        try:
            bounds.append(datetime.fromisoformat(value).timestamp() if value else None)
        except ValueError:
            bounds.append(None)
    start, end = bounds
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
            rows = c.execute("SELECT content,timestamp FROM messages WHERE content LIKE '[CONTEXT COMPACTION%'").fetchall()
    except sqlite3.Error:
        return None, None
    chosen = [content for content, ts in rows if (start is None or ts >= start - 1) and (end is None or ts <= end + 1)]
    return len(chosen), sum("deterministic fallback" in content for content in chosen)


def stream_compactions(parsed):
    """Compaction markers the harness wrote into its stream, as {line, text}: Hermes's plain-text
    "⟳ compacting context…" (parsed as `runtime_status`) and Claude Code's `system` event with subtype
    `compact_boundary` (its `compact_metadata` names the trigger and the context size before compaction)."""
    found = []
    for entry in parsed.get("events", []):
        event = entry["event"]
        if event.get("type") == "runtime_status":
            found.append({"line": entry["line"], "text": str(event.get("text", "")).strip()})
        elif event.get("type") == "system" and event.get("subtype") == "compact_boundary":
            meta = event.get("compact_metadata") if isinstance(event.get("compact_metadata"), dict) else {}
            detail = ", ".join(f"{k} {meta[k]}" for k in ("trigger", "pre_tokens") if meta.get(k) is not None)
            found.append({"line": entry["line"], "text": "compact_boundary" + (f" ({detail})" if detail else "")})
    return found


def compactions_reported(harness_name, config=None):
    """The adapter's capability flag: does this harness's stream mark context compactions?"""
    from daw import harness
    from daw.util import DawError
    try:
        return harness.get(harness_name).reports_compactions(config or {})
    except DawError:
        return False


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def suspension_seconds(wall, mono):
    """Wall minus monotonic beyond the floor; 0 when both clocks were recorded and the gap is under the
    floor (measured, none); None when either clock is unavailable (C10: never a defaulted zero)."""
    if not (_number(wall) and _number(mono)):
        return None
    return round(wall - mono, 1) if wall - mono > SUSPENSION_FLOOR_SECONDS else 0


def run_metrics(folder, parsed, *, compactions_reported=True):
    """Behavioural counts from one delivery. Wall time includes host sleep; monotonic does not.

    A value whose source was not recorded is None ("unavailable"), never 0 (spec v2 C10): clocks missing
    from execution.json, every stream count when the run has no events.jsonl, compactions for a harness
    whose stream does not mark them (`compactions_reported`, the adapter's capability flag), analysis
    failures when no analysis reported an exit code, and the provider-citation check without a final."""
    execution = read_json(folder / "execution.json") if (folder / "execution.json").exists() else {}
    wall, mono = execution.get("wall_seconds"), execution.get("monotonic_seconds")
    stream = (folder / "events.jsonl").is_file()
    tools = [i for i in parsed["items"] if i.get("type") != "agent_message"]
    commands = [i["command"] for i in tools if i.get("name") == "terminal"]
    analyses = [i for i in tools if i.get("name") == "terminal" and "run_analysis.py" in i["command"]]
    writes = [i["input"].get("path", "") for i in tools if i.get("name") == "write_file"]
    scripts = [p for p in writes if p.endswith(".py")]
    stamps = [e["event"].get("timestamp") for e in parsed["events"] if _number(e["event"].get("timestamp"))]
    last_ok = [e for e in parsed["events"] if e["event"].get("type") == "tool_result"
               and any(a.get("result_line") == e["line"] and a.get("exit_code") == 0 for a in analyses)]
    tail = None
    suspended = suspension_seconds(wall, mono)
    if last_ok and stamps and not suspended:
        # Stream timestamps are wall clock; a host suspension inside the span would inflate the tail (v3.1).
        tail = round((max(stamps) - last_ok[-1]["event"].get("timestamp", max(stamps))) / 60000, 1)
    final = folder / "final.md"
    summaries, fallbacks = compaction_summaries(folder, execution)
    results = [str(e["event"].get("output") or "") for e in parsed["events"] if e["event"].get("type") == "tool_result"]
    reads = [i["input"].get("path", "") for i in tools if i.get("name") == "read_file"]
    known_exit = [a for a in analyses if a.get("exit_code") is not None]

    def count(value):
        return value if stream else None
    return {"wall_seconds": wall if _number(wall) else None, "monotonic_seconds": mono if _number(mono) else None,
            "suspended_seconds": suspension_seconds(wall, mono),
            "compaction_summaries": summaries, "compaction_fallbacks": fallbacks,
            "tool_calls": count(len(tools)), "terminal_commands": count(len(commands)),
            "help_calls": count(sum("--help" in c for c in commands)),
            "inbox_calls": count(sum("community inbox" in c for c in commands)),
            "forum_searches": count(sum("community search" in c for c in commands)),
            "library_family_searches": count(sum("--family" in c and "community search" in c for c in commands)),
            "overview_calls": count(sum("community overview" in c for c in commands)),
            "frontier_reads": count(sum(bool(re.search(r"community (?:frontier|experiments)\b", c)) for c in commands)),
            "analysis_receipts": count(len(analyses)),
            "analysis_failures": count(sum(1 for a in known_exit if a["exit_code"] != 0)) if known_exit or not analyses else None,
            "analysis_exit_codes_unknown": count(len(analyses) - len(known_exit)),
            "registrations": count(sum(bool(re.search(r"\bbio\s+register\b", c)) for c in commands)),
            "scripts_written": count(len(scripts)),
            "plumbing_scripts": count(sum(bool(PLUMBING.search(Path(p).name)) for p in scripts)),
            "compactions": count(len(stream_compactions(parsed)))
            if compactions_reported else None,
            # Agent-efficiency counters from the transcript review (2026-10-07); each names a cohort failure mode.
            "no_such_command": count(sum("No such command" in r for r in results)),          # guessed CLI verbs (25)
            "unknown_artifact_errors": count(sum("unknown_artifact" in r for r in results)),  # unpublished citations (16 runs)
            "truncated_terminal_results": count(sum("truncation_note" in r for r in results)),  # compound-command captures (58)
            "verify_scripts_written": count(sum(bool(VERIFY.search(Path(p).name)) for p in scripts)),  # 69 hand-written
            "inspection_scripts_written": count(sum(bool(INSPECT.search(Path(p).name)) for p in scripts)),  # 169 hand-written
            "labbook_reads": count(sum(Path(p).name == "LABBOOK.md" for p in reads)),  # 100 repeats, 86% prompt-habit
            "resume_calls": count(sum("work resume" in c for c in commands)),
            "records_helper_calls": count(sum("records.py" in c for c in commands)),
            "empty_final": (not final.read_text().strip()) if final.exists() else None,
            "minutes_after_last_successful_analysis": tail,
            "provider_citation_in_final": bool(PROVIDER_CITATION.search(final.read_text())) if final.exists() else None,
            "limitations": ["events.jsonl truncates tool outputs at 5000 chars; model-facing bodies are in agent-state/state.db",
                            "minutes_after_last_successful_analysis is None when a host suspension lies in the stream's span",
                            "no assistant reasoning is streamed between tool calls; gaps are generation or suspension",
                            "None means unavailable (not recorded or not emitted by this harness), never zero"]}
