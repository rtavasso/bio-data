from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    question: str = Field(min_length=1, max_length=20000)
    setup: Literal["zero-vs-missing", "artifact-reuse", "limited-context", "empty"] = "empty"
    data_access: Literal["offline", "public"] = "offline"
    skills: list[Literal["bio-research", "bio-data-discovery", "bio-artifact-reuse"]] = Field(default_factory=lambda: ["bio-research"])
    review_focus: list[str] = Field(default_factory=list)
    expect: list[Literal["question", "notebook", "script", "registered_output", "reuse", "gap"]] = Field(default_factory=lambda: ["question", "notebook"])


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
