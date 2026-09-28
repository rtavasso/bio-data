"""Read-only check of current discovery IDs and exact prediction bytes, including inherited records."""
import argparse
import hashlib
import json
import re
from pathlib import Path


SCOPE = "Identity/hash checks only; schema, provenance, exposure timing, independence and scientific validity require separate review."


def read_object(path, limit):
    if path.stat().st_size > limit:
        raise ValueError(f"file exceeds {limit} bytes")
    data = path.read_bytes()
    value = json.loads(data)
    json.dumps(value, allow_nan=False)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return data, value


def check_links(question):
    question = question.resolve()
    errors = []
    checked = 0
    _, ledger = read_object(question / "outputs/discoveries.json", 4 * 2**20)
    candidates = ledger.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    seen = set()
    for index, candidate in enumerate(candidates):
        label = f"candidate[{index}]"
        try:
            if not isinstance(candidate, dict):
                raise ValueError("candidate must be an object")
            identifier = candidate.get("id")
            if not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", identifier):
                raise ValueError("invalid candidate id")
            label = identifier
            if identifier in seen:
                raise ValueError("duplicate candidate id")
            seen.add(identifier)
            lock, expected = candidate.get("prediction_lock"), candidate.get("prediction_sha256")
            if bool(lock) != bool(expected):
                raise ValueError("prediction file and hash must be recorded together")
            if not lock:
                if candidate.get("prediction_id") or candidate.get("validation_mode") == "prospective":
                    raise ValueError("prediction link required")
                continue
            checked += 1
            if not isinstance(lock, str) or Path(lock).is_absolute():
                raise ValueError("prediction path must be question-relative")
            path = (question / lock).resolve()
            if not path.is_relative_to(question):
                raise ValueError("prediction path escapes question")
            data, prediction = read_object(path, 2**20)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("prediction bytes do not match recorded hash")
            prediction_id = candidate.get("prediction_id") or identifier
            if prediction.get("candidate_id") != prediction_id:
                raise ValueError("prediction belongs to another candidate")
            if prediction_id != identifier:
                members = prediction.get("candidate_ids")
                if (not isinstance(members, list) or not members
                        or any(not isinstance(m, str) or not m.strip() for m in members)
                        or len(set(members)) != len(members) or identifier not in members):
                    raise ValueError("candidate is not an explicit member of the sealed prediction family")
        except (OSError, ValueError) as error:
            errors.append({"candidate": label, "error": str(error)})
    return {"valid": not errors, "candidates_checked": len(candidates), "prediction_links_checked": checked,
            "errors": errors, "scope": SCOPE}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", type=Path)
    args = parser.parse_args()
    try:
        result = check_links(args.question)
    except (OSError, ValueError) as error:
        result = {"valid": False, "errors": [{"error": str(error)}], "scope": SCOPE}
    print(json.dumps(result, allow_nan=False, indent=2))
    raise SystemExit(0 if result["valid"] else 1)
