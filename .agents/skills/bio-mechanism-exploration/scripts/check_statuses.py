"""Read-only JSON, status and coverage-header check; no reference or science validation."""
import csv
import json
import sys
from pathlib import Path

EDGE = {"hypothesis", "supported", "contested", "rejected"}
FRONTIER = {"open", "investigated", "deferred"}
QUEUE = {"in_progress", "bounded_complete"}
ITEM = {"open", "ready", "running", "analyzed", "blocked", "deferred"}
PRIORITY = {"high", "medium", "low"}
COVERAGE = {"not_searched", "searched", "located", "inspected", "analyzed", "unavailable"}
COVERAGE_FIELDS = {"edge_ids", "alternatives", "observation", "file_or_accession", "analysis", "inspection_status",
                   "source_locator", "result_or_limitation", "next_action"}


def check(question):
    outputs = Path(question) / "outputs"
    errors = []

    def status(value, allowed, location):
        if not isinstance(value, str) or value not in allowed:
            errors.append(f"{location}: expected {sorted(allowed)}, got {value!r}")

    def reject_constant(value):
        raise ValueError(f"nonstandard JSON constant {value}")

    for name in ("mechanisms.json", "investigations.json", "evidence-coverage.tsv"):
        path = outputs / name
        if name == "investigations.json" and not path.exists():
            continue  # Short mechanism investigations need not have a sustained-work queue.
        try:
            if path.stat().st_size > 4 * 2**20:
                raise ValueError("exceeds 4 MiB check limit")
            if path.suffix == ".tsv":
                with path.open(encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream, delimiter="\t")
                    missing = COVERAGE_FIELDS - set(reader.fieldnames or [])
                    if missing:
                        errors.append(f"{name}: missing columns {sorted(missing)}")
                    for n, row in enumerate(reader, 2):
                        status(row.get("inspection_status"), COVERAGE, f"{name}:line {n}/inspection_status")
                continue
            value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
            fields = (("edges", EDGE), ("frontier", FRONTIER)) if name == "mechanisms.json" else (("items", ITEM),)
            if name == "investigations.json":
                status(value["status"], QUEUE, f"{name}/status")
            for field, allowed in fields:
                if not isinstance(value[field], list):
                    raise ValueError(f"{field} must be a list")
                for n, item in enumerate(value[field]):
                    status(item["status"], allowed, f"{name}/{field}/{n}/status")
                    if field == "items":
                        status(item["priority"], PRIORITY, f"{name}/{field}/{n}/priority")
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"{name}: {error}")
    return {"valid": not errors, "errors": errors,
            "scope": "Current-file JSON syntax, status vocabulary and coverage columns only; reference integrity, closure and scientific validity need separate review."}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python check_statuses.py QUESTION_DIRECTORY")
    result = check(sys.argv[1])
    print(json.dumps(result, indent=2, allow_nan=False))
    raise SystemExit(0 if result["valid"] else 1)
