"""Read-only collaboration audit using the existing transcript machinery.

Run: uv run python -m benchmarks.agent.community --community PATH --output PATH
This records observable reuse links, evidence acquisition and per-run behaviour
metrics (clock, ceremony, polling, provenance lint), not novelty scores.
"""
import argparse
import json
from pathlib import Path

from daw import harness
from daw.artifacts import reuse_links
from daw.catalog import Workspace
from daw.commons.metrics import task_type_of
from daw.commons.runmetrics import PLUMBING, SUSPENSION_FLOOR_SECONDS, compaction_summaries, run_metrics  # noqa: F401
from daw.community import PROVIDER_CITATION, Community
from daw.util import file_hash, now, write_json

def report(root, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with Community(root) as board:
        audit = board.audit()
        runs = []
        requests = {r["id"]: r for r in audit["requests"]}
        for attempt in audit["attempts"]:
            folder = board.root / attempt["path"]
            raw = folder / "events.jsonl"
            parsed = harness.for_agent(board.agent(attempt["target"])).parse(raw)
            request = requests[attempt["request"]]
            runs.append({**attempt, "transcript": str(folder / "transcript.md"),
                         "harness": board.agent(attempt["target"])["config"].get("harness", "hermes"),
                         "task_type": task_type_of(request, board.show(request["post"])["content"]),
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
                   "wall_hours": round(sum((r["metrics"]["wall_seconds"] or 0) for r in runs) / 3600, 2),
                   "monotonic_hours": round(sum((r["metrics"]["monotonic_seconds"] or 0) for r in runs) / 3600, 2),
                   "suspended_hours": round(sum(r["metrics"]["suspended_seconds"] for r in runs) / 3600, 2),
                   "notification_runs": len(notifications),
                   "compaction_summaries": sum(r["metrics"]["compaction_summaries"] or 0 for r in runs),
                   "compaction_fallbacks": sum(r["metrics"]["compaction_fallbacks"] or 0 for r in runs),
                   "reused_links": sum(1 for r in reuse if r["relationship"] == "reused"),
                   "reused_links_backed": sum(1 for r in reuse if r["relationship"] == "reused" and r.get("backed")),
                   "plumbing_scripts": sum(r["metrics"]["plumbing_scripts"] for r in runs),
                   "scripts_written": sum(r["metrics"]["scripts_written"] for r in runs),
                   "suspensions": sum(1 for r in runs if r["metrics"]["suspended_seconds"]),
                   "tool_calls": sum(r["metrics"]["tool_calls"] for r in runs),
                   "inbox_calls": sum(r["metrics"]["inbox_calls"] for r in runs),
                   "analysis_receipts": sum(r["metrics"]["analysis_receipts"] for r in runs),
                   "analysis_failures": sum(r["metrics"]["analysis_failures"] for r in runs),
                   "harnesses": ", ".join(sorted({r["harness"] for r in runs})) or "none",
                   "task_types": ", ".join(sorted({r["task_type"] for r in runs})) or "none",
                   "posts_with_provider_citations": len(lint),
                   "finals_with_provider_citations": sum(1 for r in runs if r["metrics"]["provider_citation_in_final"])}
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
              "| Request | State | Agent | Harness | Task type | monotonic min | suspended min | tools | analyses (failed) | plumbing/scripts | inbox | compactions (fallbacks) | tail min | Transcript |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for run in runs:
        m = run["metrics"]
        mono = round((m["monotonic_seconds"] or 0) / 60, 1)
        lines.append(f"| {run['request']} | {run['state']} | {run['target']} | {run['harness']} | {run['task_type']} | {mono} | {round(m['suspended_seconds'] / 60, 1)} | "
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
