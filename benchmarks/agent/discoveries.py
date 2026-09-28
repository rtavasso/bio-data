"""Inspect discovery records without certifying novelty, independence or prediction timing."""
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from daw.util import file_hash, read_json

from .runner import safe_path


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
