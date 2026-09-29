"""Inspect discovery records without certifying novelty, independence or prediction timing."""
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from daw.util import file_hash, read_json


def safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("expected a relative path inside the run")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise ValueError("run paths must not escape through symlinks")
    return path

class Record(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


class PriorWork(Record):
    source: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    relationship: str = Field(min_length=1)


class Search(Record):
    query: str = Field(min_length=1)
    date: date
    evidence: str = Field(min_length=1)


class Novelty(Record):
    status: Literal["known", "not_found_in_scoped_search", "unresolved"]
    closest_prior_work: list[PriorWork]
    searches: list[Search]
    limitation: str = Field(min_length=1)

    @model_validator(mode="after")
    def search_boundary(self):
        if self.status != "unresolved" and not self.closest_prior_work:
            raise ValueError("novelty assessment needs closest prior work")
        if self.status == "not_found_in_scoped_search" and not self.searches:
            raise ValueError("not-found assessment needs preserved searches")
        return self


class Candidate(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    claim: str = Field(min_length=1)
    context: str = Field(min_length=1)
    kind: Literal["biological", "analytical"]
    status: Literal["candidate", "supported_in_scope", "contradicted", "unresolved", "reproduced_known"]
    alternatives: list[str] = Field(min_length=2)
    discovery_artifacts: list[str] = Field(min_length=1)
    prediction_lock: str | None
    prediction_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_id: str | None = Field(default=None, min_length=1)
    validation_mode: Literal["prospective", "retrospective", "not_tested"]
    validation_artifacts: list[str]
    validation_result: str = Field(min_length=1)
    independence_assessment: str = Field(min_length=1)
    novelty: Novelty
    limitations: str = Field(min_length=1)
    next_test: str = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_boundary(self):
        if bool(self.prediction_lock) != bool(self.prediction_sha256):
            raise ValueError("prediction file and hash must be recorded together")
        if self.prediction_id and not self.prediction_lock:
            raise ValueError("prediction_id requires a sealed prediction")
        if self.validation_mode == "prospective" and not self.prediction_lock:
            raise ValueError("prospective claim requires sealed prediction")
        if self.validation_mode != "not_tested" and not self.validation_artifacts:
            raise ValueError("tested claim requires validation artifacts")
        if self.validation_mode == "not_tested" and self.validation_artifacts:
            raise ValueError("untested claim cannot list validation artifacts")
        if self.status in {"supported_in_scope", "contradicted"} and self.validation_mode == "not_tested":
            raise ValueError("supported or contradicted claim requires a test")
        return self


class DiscoveryLedger(Record):
    revision: int = Field(ge=1, strict=True)
    scope: str = Field(min_length=1)
    known_baseline: str = Field(min_length=1)
    budget_allocation: str = Field(min_length=1)
    stopping_reason: str = Field(min_length=1)
    candidates: list[Candidate]
    no_candidates_reason: str

    @model_validator(mode="after")
    def candidate_boundary(self):
        if len({c.id for c in self.candidates}) != len(self.candidates):
            raise ValueError("duplicate candidate IDs")
        if not self.candidates and not self.no_candidates_reason:
            raise ValueError("an empty ledger needs an evidenced explanation")
        return self


def inspect_candidate(folder, candidate, artifact_ids, parsed):
    if not set(candidate.discovery_artifacts + candidate.validation_artifacts) <= artifact_ids:
        raise ValueError("candidate refers to an unregistered or unlinked artifact")
    for search in candidate.novelty.searches:
        if not safe_path(folder, search.evidence).is_file():
            raise ValueError("novelty search evidence is absent")
    seal_lines = []
    if candidate.prediction_lock:
        prediction = safe_path(folder, candidate.prediction_lock)
        if prediction.stat().st_size > 2**20 or file_hash(prediction) != candidate.prediction_sha256:
            raise ValueError("prediction bytes do not match their recorded hash")
        prediction_value = read_json(prediction)
        prediction_id = candidate.prediction_id or candidate.id
        if not isinstance(prediction_value, dict) or prediction_value.get("candidate_id") != prediction_id:
            raise ValueError("prediction belongs to another candidate")
        if prediction_id != candidate.id:
            members = prediction_value.get("candidate_ids")
            if (not isinstance(members, list) or not members
                    or any(not isinstance(m, str) or not m.strip() for m in members)
                    or len(set(members)) != len(members) or candidate.id not in members):
                raise ValueError("candidate is not an explicit member of the sealed prediction family")
        # These are review leads, not proof of prior execution or a blinded test.
        for item in parsed["items"]:
            if (item.get("type") == "command_execution" and item.get("exit_code") == 0
                    and "seal_prediction.py" in item.get("command", "")):
                for line in item.get("aggregated_output", "").splitlines():
                    try:
                        receipt = json.loads(line)
                    except ValueError:
                        continue
                    if (isinstance(receipt, dict) and receipt.get("event") == "prediction_sealed"
                            and receipt.get("candidate_id") == prediction_id
                            and receipt.get("sha256") == candidate.prediction_sha256):
                        seal_lines.append(item["line"])
    return {"id": candidate.id, "kind": candidate.kind, "status": candidate.status,
            "novelty": candidate.novelty.status, "validation_mode": candidate.validation_mode,
            "prediction_id": (candidate.prediction_id or candidate.id) if candidate.prediction_lock else None,
            "prediction_lock": candidate.prediction_lock, "prediction_sha256": candidate.prediction_sha256,
            "seal_receipt_lines": sorted(set(seal_lines))}


def inspect_discoveries(trial, question, artifact_ids, parsed, *, collect_errors=False, baseline_value=None):
    folder = safe_path(trial / "workspace", question["path"])
    path = safe_path(folder, "outputs/discoveries.json")
    if path.stat().st_size > 4 * 2**20:
        raise ValueError("discovery ledger exceeds 4 MiB inspection budget")
    value = read_json(path)
    json.dumps(value, allow_nan=False)
    ledger = DiscoveryLedger.model_validate(value)
    records, errors = [], []
    prior_candidates = baseline_value.get("candidates", []) if isinstance(baseline_value, dict) else []
    prior = {c["id"]: c for c in prior_candidates if isinstance(c, dict) and isinstance(c.get("id"), str)}
    for candidate in ledger.candidates:
        try:
            records.append(inspect_candidate(folder, candidate, artifact_ids, parsed))
        except (ValueError, OSError) as error:
            if not collect_errors:
                raise
            previous = prior.get(candidate.id)
            fields = ("id", "prediction_id", "prediction_lock", "prediction_sha256")
            errors.append({"id": candidate.id, "error": str(error),
                           "prediction_reference_unchanged_from_baseline": bool(previous is not None and
                               all(previous.get(k) == getattr(candidate, k) for k in fields))})
    result = {"question": question["id"], "revision": ledger.revision, "candidates": records,
              "candidate_errors": errors,
              "note": "Record integrity only. Receipt lines are review leads; assess outcome exposure, independence, claim support and novelty from source/transcript evidence."}
    if errors:
        result["error"] = f"{len(errors)} candidate reference error(s); valid candidates are retained for review"
    return result


class Investigation(Record):
    id: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    question: str = Field(min_length=1)
    alternatives: list[str] = Field(min_length=2)
    readout: str = Field(min_length=1)
    assets: list[str]
    prerequisites: list[str]
    status: Literal["open", "ready", "running", "analyzed", "blocked", "deferred"]
    artifacts: list[str]
    finding: str
    limitation: str
    next_action: str = Field(min_length=1)
    blocker_evidence: list[str]  # Paths relative to the question, not arbitrary host paths.

    @model_validator(mode="after")
    def evidenced_disposition(self):
        if self.status == "analyzed" and (not self.artifacts or not self.finding.strip()):
            raise ValueError("analyzed investigation requires registered results and a finding")
        if self.status == "blocked" and (not self.blocker_evidence or not self.limitation.strip()):
            raise ValueError("blocked investigation requires preserved evidence and a specific limitation")
        if self.status == "deferred" and not self.limitation.strip():
            raise ValueError("deferral requires a reason and remains unfinished")
        return self


class InvestigationQueue(Record):
    revision: int = Field(ge=1, strict=True)
    scope: str = Field(min_length=1)
    status: Literal["in_progress", "bounded_complete"]
    stopping_reason: str = Field(min_length=1)
    items: list[Investigation] = Field(min_length=1)

    @model_validator(mode="after")
    def honest_closure(self):
        if len({i.id for i in self.items}) != len(self.items):
            raise ValueError("duplicate investigation IDs")
        if not any(i.priority == "high" for i in self.items):
            raise ValueError("declare at least one high-priority investigation")
        if self.status == "bounded_complete" and any(
                i.priority == "high" and i.status not in {"analyzed", "blocked"} for i in self.items):
            raise ValueError("open or deferred high-priority work is not bounded complete")
        return self


def inspect_queue(trial, question, artifact_ids):
    folder = safe_path(trial / "workspace", question["path"])
    path = safe_path(folder, "outputs/investigations.json")
    if path.stat().st_size > 4 * 2**20:
        raise ValueError("investigation queue exceeds 4 MiB inspection budget")
    queue = InvestigationQueue.model_validate(read_json(path))
    for item in queue.items:
        if not set(item.artifacts) <= artifact_ids:
            raise ValueError("investigation refers to an unregistered or unlinked artifact")
        for evidence in item.blocker_evidence:
            if not safe_path(folder, evidence).is_file():
                raise ValueError("blocker evidence file is absent")
    return {"question": question["id"], "revision": queue.revision, "status": queue.status,
            "stopping_reason": queue.stopping_reason,
            "items": [{"id": i.id, "priority": i.priority, "status": i.status, "artifacts": i.artifacts}
                      for i in queue.items]}


def check_handoff(question):
    """Read-only schema, exact prediction and registered-reference checks, no science grading."""
    import sqlite3
    from contextlib import closing

    question = Path(question).resolve()
    workspace = question.parent.parent
    if question.parent.name != "questions":
        raise ValueError("expected WORKSPACE/questions/QUESTION")
    with closing(sqlite3.connect((workspace / "catalog.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT id,path FROM question WHERE id=?", (question.name,)).fetchone()
        if row is None or safe_path(workspace, row["path"]).resolve() != question:
            raise ValueError("question is not registered at this path")
        artifacts = {r[0] for r in db.execute(
            "SELECT qa.artifact_id FROM question_artifact qa JOIN artifact a ON a.id=qa.artifact_id WHERE qa.question_id=?",
            (row["id"],))}
    errors, checked = [], []
    ledger_path = question / "outputs/discoveries.json"
    queue_path = question / "outputs/investigations.json"
    for label, path in (("discovery_ledger", ledger_path), ("investigation_queue", queue_path)):
        if not path.exists():
            continue
        try:
            if path.stat().st_size > 4 * 2**20:
                raise ValueError("record exceeds 4 MiB inspection budget")
            if label == "discovery_ledger":
                ledger = DiscoveryLedger.model_validate(read_json(path))
                for candidate in ledger.candidates:
                    inspect_candidate(question, candidate, artifacts, {"items": []})
            else:
                queue = InvestigationQueue.model_validate(read_json(path))
                for item in queue.items:
                    if not set(item.artifacts) <= artifacts:
                        raise ValueError("investigation refers to an unregistered or unlinked artifact")
                    for evidence in item.blocker_evidence:
                        if not safe_path(question, evidence).is_file():
                            raise ValueError("blocker evidence file is absent")
            checked.append(label)
        except (ValueError, OSError) as error:
            errors.append({"record": label, "error": str(error)})
    if not checked and not errors:
        errors.append({"error": "no discovery ledger or investigation queue found"})
    return {"valid": not errors, "checked": checked, "errors": errors,
            "scope": "Full record schemas, registered question links and exact prediction references; not exposure timing, retrieval execution, biological validity or novelty."}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Read-only research handoff validation")
    parser.add_argument("question", type=Path)
    args = parser.parse_args()
    try:
        result = check_handoff(args.question)
    except (ValueError, OSError) as error:
        result = {"valid": False, "errors": [{"error": str(error)}]}
    print(json.dumps(result, indent=2, allow_nan=False))
    raise SystemExit(0 if result["valid"] else 1)
