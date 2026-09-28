"""Preserve an exact prediction before testing; no scientific or timing certification."""
import argparse
import hashlib
import json
import re
from pathlib import Path


TEXT_FIELDS = ("candidate_id", "claim", "context", "baseline_model", "prior_exposure", "prediction",
               "analysis_plan", "success_rule", "failure_rule", "selection_and_multiplicity")
LIST_FIELDS = ("discovery_sources", "validation_sources", "confounder_checks")


def validate_prediction(value):
    if not isinstance(value, dict):
        raise ValueError("prediction must be a JSON object")
    for field in TEXT_FIELDS:
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError(f"{field} must be nonempty text")
    for field in LIST_FIELDS:
        if not isinstance(value.get(field), list) or not value[field] or any(
                not isinstance(s, str) or not s.strip() for s in value[field]):
            raise ValueError(f"{field} must be a nonempty list of text")
    if "candidate_ids" in value:
        members = value["candidate_ids"]
        if (not isinstance(members, list) or not members
                or any(not isinstance(m, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", m) for m in members)
                or len(set(members)) != len(members)):
            raise ValueError("candidate_ids must be a nonempty list of unique ledger candidate IDs")
    # Reject non-finite values anywhere, including optional fields.
    json.dumps(value, allow_nan=False)
    return value


def seal(source, destination):
    if source.stat().st_size > 1024 * 1024:
        raise ValueError("prediction exceeds 1 MiB")
    data = source.read_bytes()
    value = validate_prediction(json.loads(data))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(data)
    return {"event": "prediction_sealed", "candidate_id": value["candidate_id"],
            "path": str(destination), "sha256": hashlib.sha256(data).hexdigest(),
            "note": "Exact bytes preserved. Review exposure history and transcript order before prospective credit."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(seal(args.source, args.destination), allow_nan=False))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Cannot seal prediction: {error}\n")
