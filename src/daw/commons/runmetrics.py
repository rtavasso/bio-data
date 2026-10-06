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


def run_metrics(folder, parsed):
    """Behavioural counts from one delivery. Wall time includes host sleep; monotonic does not."""
    execution = read_json(folder / "execution.json") if (folder / "execution.json").exists() else {}
    wall, mono = execution.get("wall_seconds"), execution.get("monotonic_seconds")
    suspended = round(wall - mono, 1) if isinstance(wall, (int, float)) and isinstance(mono, (int, float)) and wall - mono > SUSPENSION_FLOOR_SECONDS else 0
    tools = [i for i in parsed["items"] if i.get("type") != "agent_message"]
    commands = [i["command"] for i in tools if i.get("name") == "terminal"]
    analyses = [i for i in tools if i.get("name") == "terminal" and "run_analysis.py" in i["command"]]
    writes = [i["input"].get("path", "") for i in tools if i.get("name") == "write_file"]
    scripts = [p for p in writes if p.endswith(".py")]
    stamps = [e["event"].get("timestamp") for e in parsed["events"] if isinstance(e["event"].get("timestamp"), (int, float))]
    last_ok = [e for e in parsed["events"] if e["event"].get("type") == "tool_result"
               and any(a.get("result_line") == e["line"] and a.get("exit_code") == 0 for a in analyses)]
    tail = None
    if last_ok and stamps:
        tail = round((max(stamps) - last_ok[-1]["event"].get("timestamp", max(stamps))) / 60000, 1)
    final = folder / "final.md"
    final_text = final.read_text() if final.exists() else ""
    summaries, fallbacks = compaction_summaries(folder, execution)
    return {"wall_seconds": wall, "monotonic_seconds": mono, "suspended_seconds": suspended,
            "compaction_summaries": summaries, "compaction_fallbacks": fallbacks,
            "tool_calls": len(tools), "terminal_commands": len(commands),
            "help_calls": sum("--help" in c for c in commands),
            "inbox_calls": sum("community inbox" in c for c in commands),
            "forum_searches": sum("community search" in c for c in commands),
            "library_family_searches": sum("--family" in c and "community search" in c for c in commands),
            "analysis_receipts": len(analyses), "analysis_failures": sum(1 for a in analyses if a.get("exit_code") not in (0, None)),
            "registrations": sum(bool(re.search(r"\bbio\s+register\b", c)) for c in commands),
            "scripts_written": len(scripts), "plumbing_scripts": sum(bool(PLUMBING.search(Path(p).name)) for p in scripts),
            "compactions": sum(1 for e in parsed["events"] if e["event"].get("type") == "runtime_status"),
            "minutes_after_last_successful_analysis": tail,
            "provider_citation_in_final": bool(PROVIDER_CITATION.search(final_text)),
            "limitations": ["events.jsonl truncates tool outputs at 5000 chars; model-facing bodies are in agent-state/state.db",
                            "no assistant reasoning is streamed between tool calls; gaps are generation or suspension"]}
