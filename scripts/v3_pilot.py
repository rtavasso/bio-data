"""Reproduce recorded v3 comparisons offline and register their provenance.

Run as: uv run python -m scripts.v3_pilot --root workspaces/v3-evaluation
This reads authored run files; it does not fabricate discoveries, review biology,
run agents, fetch data, or reconstruct absent source receipts.
"""
import argparse
from pathlib import Path

from benchmarks.evaluate import evaluate
from daw.artifacts import register_artifact
from daw.catalog import Workspace
from daw.gaps import report_gaps
from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
from daw.util import canonical, environment_identity, file_hash, now, read_json, write_json
from daw.work import create_question, record_event, sync_work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, default=Path("docs/v3/receipts/evaluation.json"))
    args = parser.parse_args()
    root = args.root
    runs = {name: read_json(root / name / "run.json") for name in ("retrieval", "prior")}
    reports = {name: evaluate(run) for name, run in runs.items()}
    ws = Workspace(root / "workspace")
    question_file = root / "question-map.json"
    questions = read_json(question_file) if question_file.exists() else {}
    registrations = {}
    try:
        with ws.writer():
            for key, title in runs["retrieval"]["question_prompts"].items():
                if key not in questions:
                    questions[key] = create_question(ws, title)["question"]
            write_json(question_file, questions)
            for gap in runs["retrieval"].get("gaps", []):
                payload = {k: v for k, v in gap.items() if k != "question_key"}
                qid = questions[gap["question_key"]]
                existing = [read_json(ws.blob_path(e["body_blob"])) for e in ws.rows(
                    "SELECT body_blob FROM work_event WHERE question_id=? AND kind='retrieval_gap'", (qid,))]
                # An offline replay must not inflate recurrence counts.
                if {**payload, "question": qid} not in existing:
                    record_event(ws, qid, "retrieval_gap", payload)
            code = [ws.put_file(Path(p), "code") for p in ("benchmarks/evaluate.py", "scripts/v3_pilot.py")]
            for name, report in reports.items():
                output = root / name / "report.json"
                write_json(output, report)
                source = ws.put_file(root / name / "run.json", "work")
                registrations[name] = register_artifact(ws, output, ArtifactRegistration(
                    title=f"V3 exploratory {name} comparison",
                    summary="Recorded candidates and attributed judgments; uncertainty and incomplete costs preserved.",
                    derivation=Derivation(inputs=[ObjectInput(blob=source, role="authored benchmark run")], code=code,
                        parameters={"comparison": name}, references=[], environment=environment_identity(),
                        command=["uv", "run", "python", "-m", "benchmarks.evaluate", str(root / name / "run.json"), "--output", str(output)]),
                    limitations=runs[name].get("limitations", [])))
            gaps = report_gaps(ws)
            write_json(root / "gap-report.json", gaps)
            for key, qid in questions.items():
                row = ws.one("SELECT path FROM question WHERE id=?", (qid,))
                results = next(q for q in reports["retrieval"]["questions"] if q["question"] == key)
                (ws.root / row["path"] / "LABBOOK.md").write_text(
                    f"# {runs['retrieval']['question_prompts'][key]}\n\n"
                    "Exploratory retrieval evaluation completed; scientific question remains open.\n\n"
                    f"Common opportunities: {', '.join(results['common']) or 'none'}. "
                    f"Additional local candidates: {', '.join(results['deep_index_only']) or 'none'}. "
                    f"Established valuable index-only opportunities: {len(results['scientifically_valuable_index_only'])}.\n\n"
                    "Read the attributed reviews in retrieval/run.json and the report artifact. "
                    "Missing cells, sample independence, contrast semantics and context transfer remain unresolved unless sourced. "
                    "Retrieval-gap events preserve failed routes and proposed follow-up. No experiment or mechanism is disproven by a missing hit.\n")
                sync_work(ws, qid, summary="V3 exploratory retrieval comparison and actual access gaps; biological conclusion remains open")
            receipt = {"created": now(), "version": "0.3.0", "root": str(root),
                "protocol": runs["retrieval"]["protocol"], "questions": questions,
                "runs": {name: {"input_sha256": reports[name]["input_sha256"],
                    "file_sha256": file_hash(root / name / "run.json"), "report_sha256": file_hash(root / name / "report.json"),
                    "artifact": registrations[name]["artifact"]} for name in runs},
                "retrieval": {k: reports["retrieval"][k] for k in ("totals", "questions", "cost", "limitations")},
                "prior": {k: reports["prior"][k] for k in ("counts", "database_only_assessments", "review_complete", "cost", "limitations")},
                "prior_reviewed_pairs": [{k: r[k] for k in ("source", "target", "importance", "reason")} for r in runs["prior"]["reviews"]],
                "gaps": {"matching_events": gaps["matching_events"], "scan_complete": gaps["scan_complete"],
                    "groups": [{k: g[k] for k in ("source_or_format", "gap_key", "observations", "distinct_questions")} for g in gaps["groups"]]},
                "decision": "Retain runtime federation and existing readers. No unique valuable index discovery established here; investigate source/sample context and annotation gaps before proposing expansion."}
            write_json(args.receipt, receipt)
            print(canonical({"retrieval": receipt["retrieval"]["totals"], "prior": receipt["prior"]["counts"],
                   "assessments": receipt["prior"]["database_only_assessments"], "receipt": str(args.receipt)}).decode())
    finally:
        ws.close()


if __name__ == "__main__":
    main()
