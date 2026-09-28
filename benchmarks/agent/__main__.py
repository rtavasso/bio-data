"""Prepare, run and inspect evaluations of a stock research agent with optional limits."""
import argparse
import os
from pathlib import Path

from daw.util import canonical, read_json, write_json

from .report import build_report, compare
from .review import review_run
from .models import ResearchBudget
from .runner import DEFAULT_TIMEOUT, prepare, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "run"):
        sub = commands.add_parser(name, help="Create isolated inputs offline" if name == "prepare" else "Launch stock Codex; requires DAW_LIVE=1")
        sub.add_argument("--suite", default="workflow", help="workflow, research, mechanisms, mechanisms-deep, mechanism-challenges, discovery, discovery-iteration, or a suite JSON path")
        sub.add_argument("--case", action="append", default=[], dest="cases")
        sub.add_argument("--output", type=Path, default=Path("workspaces/agent-evals"))
        sub.add_argument("--skills", choices=("on", "off"), default="on")
        sub.add_argument("--profile", choices=("pilot", "deep"), default="pilot", help="Research instructions; both profiles have unlimited budgets by default")
        sub.add_argument("--timeout", type=int, help="Wall seconds per case; default 0 means unlimited")
        sub.add_argument("--requests", type=int, help="Total research request allowance; default 0 means unlimited")
        sub.add_argument("--asset-mib", type=int, help="Per-file MiB allowance; default 0 means unlimited")
        sub.add_argument("--total-mib", type=int, help="Total newly downloaded MiB allowance; default 0 means unlimited")
        sub.add_argument("--model", help="Optional explicit model; otherwise stock CLI default")
        sub.add_argument("--seed-workspace", type=Path, help="Copy a preserved workspace; never give the subject the original")
        sub.add_argument("--continue-question", help="Continue this question in a copied seed workspace; one selected case required")
        if name == "run":
            sub.add_argument("--prepared", type=Path, help="Launch a prepared run without overwriting any earlier execution")
            sub.add_argument("--codex", default="codex")
            sub.add_argument("--review", action="store_true", help="Run a separate agent review after the subjects")
    report = commands.add_parser("report", help="Rebuild JSON/HTML and readable transcripts offline")
    report.add_argument("run", type=Path)
    review = commands.add_parser("review", help="Generate a review prompt, import an authored review, or launch a fresh reviewer")
    review.add_argument("run", type=Path)
    mode = review.add_mutually_exclusive_group()
    mode.add_argument("--agent", action="store_true")
    mode.add_argument("--from-json", type=Path, dest="authored")
    review.add_argument("--codex", default="codex")
    review.add_argument("--model")
    review.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Wall seconds; default 0 means unlimited")
    comparison = commands.add_parser("compare", help="Compare observed check outcomes and measured run times")
    comparison.add_argument("before", type=Path)
    comparison.add_argument("after", type=Path)
    comparison.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command in {"prepare", "run"}:
            if args.command == "run" and os.environ.get("DAW_LIVE") != "1":
                raise ValueError("agent execution requires DAW_LIVE=1; use prepare/report offline")
            root = getattr(args, "prepared", None)
            if root and any((args.cases, args.seed_workspace, args.model, args.skills != "on", args.timeout is not None,
                             args.suite != "workflow", args.profile != "pilot", args.continue_question,
                             args.requests is not None, args.asset_mib is not None, args.total_mib is not None)):
                raise ValueError("--prepared uses its recorded configuration; prepare a new run to change settings")
            limits = {k: v for k, v in {"requests": args.requests,
                "asset_bytes": args.asset_mib * 2**20 if args.asset_mib is not None else None,
                "total_bytes": args.total_mib * 2**20 if args.total_mib is not None else None}.items() if v is not None}
            root = root or prepare(args.suite, args.output, args.cases, args.skills == "on", args.timeout, args.model,
                args.seed_workspace, profile=args.profile, budget=ResearchBudget(**limits), continue_question=args.continue_question)
            if args.command == "run":
                root = run(root, args.codex)
                if args.review:
                    recorded = read_json(root / "manifest.json")
                    review_run(root, agent=True, executable=args.codex, model=recorded["requested_model"], timeout=recorded["timeout_seconds"])
            report = build_report(root)
            result = {"run": str(root), "report": str(root / "report.html"), "cases": [{"id": c["case_id"], "state": c["status"]} for c in report["cases"]]}
        elif args.command == "report":
            report = build_report(args.run)
            result = {"report": str(args.run / "report.html"), "review_state": report["review_state"],
                      "cases": [{"id": c["case_id"], "state": c["status"]} for c in report["cases"]]}
        elif args.command == "review":
            result = review_run(args.run, agent=args.agent, executable=args.codex, model=args.model, timeout=args.timeout, authored=args.authored)
        else:
            result = compare(args.before, args.after)
            if args.output:
                write_json(args.output, result)
        print(canonical(result).decode())
        if args.command == "run" and (any(c["state"] != "complete" for c in result["cases"]) or (args.review and report["review_state"] != "recorded")):
            raise SystemExit(2)
        if args.command == "review" and args.agent and result["state"] != "recorded":
            raise SystemExit(2)
    except KeyboardInterrupt:
        print(canonical({"error": "interrupted", "note": "Partial evidence and execution state retained"}).decode())
        raise SystemExit(130) from None
    except (ValueError, OSError) as e:
        print(canonical({"error": str(e)}).decode())
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
