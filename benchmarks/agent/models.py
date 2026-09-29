from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResearchBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Zero denotes an unlimited allowance, including in manifests and TOML.
    requests: int = Field(default=0, ge=0)
    asset_bytes: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def fits_total(self):
        if self.asset_bytes and self.total_bytes and self.asset_bytes > self.total_bytes:
            raise ValueError("per-file budget must fit the total budget")
        return self


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    question: str = Field(min_length=1, max_length=20000)
    setup: Literal["zero-vs-missing", "artifact-reuse", "limited-context", "mechanism-blindspots", "empty"] = "empty"
    data_access: Literal["offline", "public"] = "offline"
    skills: list[Literal["bio-research", "bio-data-discovery", "bio-artifact-reuse", "bio-mechanism-exploration", "bio-hypothesis-discovery", "bio-research-consolidation"]] = Field(default_factory=lambda: ["bio-research"])
    review_rubric: Literal["standard", "mechanism-exploration", "hypothesis-discovery"] = "standard"
    review_focus: list[str] = Field(default_factory=list)
    investigation_brief: str = Field(default="", max_length=10000)
    expect: list[Literal["question", "notebook", "script", "registered_output", "reuse", "gap", "mechanism_map", "mechanism_revision", "evidence_coverage", "investigation_queue", "executed_analysis", "discovery_ledger"]] = Field(default_factory=lambda: ["question", "notebook"])


class Suite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    description: str
    cases: list[Case] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_cases(self):
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("case IDs must be unique")
        return self


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    locator: str


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    category: Literal["agent", "skill", "tooling", "retrieval", "scientific_reasoning", "evaluation", "environment"]
    severity: Literal["low", "medium", "high"]
    observation: str
    evidence: list[Citation] = Field(min_length=1)
    suggested_change: str
    validation_test: str


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    strengths: list[str]
    findings: list[Finding]
    unresolved: list[str]
    next_experiments: list[str]


MECHANISM_CRITERIA = ("recursive_exploration", "breadth", "discovery_value", "discrimination", "revision", "calibration")
DISCOVERY_CRITERIA = ("baseline_and_selection", "prediction_timing", "independent_validation",
                      "confounder_discrimination", "novelty_audit", "claim_calibration")


class MechanismAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    criterion: Literal["recursive_exploration", "breadth", "discovery_value", "discrimination", "revision", "calibration",
                       "baseline_and_selection", "prediction_timing", "independent_validation",
                       "confounder_discrimination", "novelty_audit", "claim_calibration"]
    verdict: Literal["demonstrated", "partial", "not_demonstrated", "unresolved"]
    justification: str
    evidence: list[Citation] = Field(min_length=1)


class MechanismReview(Review):
    assessments: list[MechanismAssessment]
