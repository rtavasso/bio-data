"""Read-only collaboration audit using the existing transcript machinery.

Run: uv run python -m benchmarks.agent.community --community PATH --output PATH
This records observable reuse links, evidence acquisition and per-run behaviour
metrics (clock, ceremony, polling, provenance lint), not novelty scores.
"""
import argparse
import json
import re
from pathlib import Path

from daw import hermes
from daw.artifacts import reuse_links
from daw.catalog import Workspace
from daw.community import PROVIDER_CITATION, Community
from daw.util import file_hash, now, read_json, write_json

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


def report(root, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with Community(root) as board:
        audit = board.audit()
        runs = []
        for attempt in audit["attempts"]:
            folder = board.root / attempt["path"]
            raw = folder / "events.jsonl"
            parsed = hermes.parse(raw)
            runs.append({**attempt, "transcript": str(folder / "transcript.md"),
                         "raw_sha256": file_hash(raw) if raw.exists() else None,
                         "native_sessions": parsed["thread_ids"], "turns_completed": parsed["turns_completed"],
                         "malformed_lines": parsed["malformed_lines"], "errors": parsed["errors"],
                         "tools": len([i for i in parsed["items"] if i.get("type") != "agent_message"]),
                         "metrics": run_metrics(folder, parsed)})
        links, reuse = [], []
        for agent in audit["agents"]:
            if not agent["trial"]:
                continue
            ws = Workspace(board.root / agent["trial"] / "workspace")
            try:
                for row in ws.rows("SELECT * FROM question_artifact ORDER BY question_id,artifact_id,relationship"):
                    links.append({"agent": agent["id"], **row})
                reuse.extend({"agent": agent["id"], **row} for row in reuse_links(ws))
            finally:
                ws.close()
        kinds = {}
        for request in audit["requests"]:
            kinds[request["id"]] = board.show(request["post"])["content"]["kind"]
        notifications = [r for r in runs if kinds.get(r["request"]) == "answer_notification"]
        lint = [{"post": e["body"]["post"]} for e in audit["events"] if e["kind"] == "published"
                and PROVIDER_CITATION.search(json.dumps(board.show(e["body"]["post"])["content"]["body"]))]
        summary = {"runs": len(runs),
                   "monotonic_hours": round(sum((r["metrics"]["monotonic_seconds"] or 0) for r in runs) / 3600, 2),
                   "suspended_hours": round(sum(r["metrics"]["suspended_seconds"] for r in runs) / 3600, 2),
                   "notification_runs": len(notifications),
                   "compaction_summaries": sum(r["metrics"]["compaction_summaries"] or 0 for r in runs),
                   "compaction_fallbacks": sum(r["metrics"]["compaction_fallbacks"] or 0 for r in runs),
                   "reused_links": sum(1 for r in reuse if r["relationship"] == "reused"),
                   "reused_links_backed": sum(1 for r in reuse if r["relationship"] == "reused" and r.get("backed")),
                   "plumbing_scripts": sum(r["metrics"]["plumbing_scripts"] for r in runs),
                   "scripts_written": sum(r["metrics"]["scripts_written"] for r in runs),
                   "posts_with_provider_citations": len(lint)}
        value = {"created": now(), "community": str(board.root), "audit": audit, "runs": runs,
                 "artifact_links": links, "reuse_links": reuse, "summary": summary,
                 "limitations": ["Inherited artifact links are not new reuse; compare fork lineage and fetch events.",
                                 "A fetch or agent-authored reused link does not prove executed analysis; `backed` only means a reason or registration input exists.",
                                 "Inspect producing receipts, applicability judgments and notebook decisions before claiming scientific improvement.",
                                 "Wall clock includes host sleep; compare monotonic_seconds."]}
    write_json(output / "report.json", value)
    lines = ["# Research community audit", "", f"Community: `{root}`", "",
             "## Summary", "", "| metric | value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in summary.items()]
    lines += ["", "## Deliveries", "",
              "| Request | State | Agent | monotonic min | suspended min | tools | analyses (failed) | plumbing/scripts | inbox | compactions (fallbacks) | tail min | Transcript |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for run in runs:
        m = run["metrics"]
        mono = round((m["monotonic_seconds"] or 0) / 60, 1)
        lines.append(f"| {run['request']} | {run['state']} | {run['target']} | {mono} | {round(m['suspended_seconds'] / 60, 1)} | "
                     f"{m['tool_calls']} | {m['analysis_receipts']} ({m['analysis_failures']}) | {m['plumbing_scripts']}/{m['scripts_written']} | "
                     f"{m['inbox_calls']} | {m['compactions']} ({m['compaction_fallbacks']}) | {m['minutes_after_last_successful_analysis']} | [Read]({run['transcript']}) |")
    lines += ["", "## Evidence acquisition", ""]
    for event in audit["events"]:
        if event["kind"] == "evidence_fetched":
            body = event["body"]
            lines.append(f"- {body['reader']} fetched {', '.join(body['artifacts'])} from {body['post']} into {body['question']}.")
    lines += ["", "## Reuse links", "", "| agent | question | artifact | relationship | backed by | ", "|---|---|---|---|---|"]
    for row in reuse:
        if row["relationship"] == "reused":
            backing = row.get("reason") or (", ".join(row.get("input_to", [])) or "nothing")
            lines.append(f"| {row['agent']} | {row['question']} | {row['artifact']} | reused | {backing} |")
    lines += ["", "## Review questions", "",
              "- Did the reader discover relevant prior work before receiving artifact identifiers?",
              "- Did it inspect sample/context limits and superseding corrections?",
              "- Did actual analysis use the fetched bytes? Inspect the producing invocation receipt.",
              "- Which decision changed because of prior work? Read the LABBOOK and transcript.",
              "- Did the follow-up resume the intended session? Did the fork leave its parent's files unchanged?",
              "- How many minutes after the last successful analysis did the run spend on packaging?",
              "", *value["limitations"], ""]
    (output / "report.md").write_text("\n".join(lines))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--community", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = report(args.community, args.output)
    print(f"Saved {len(value['runs'])} delivery traces to {args.output / 'report.md'}")


if __name__ == "__main__":
    main()
