"""Small storage/provenance contracts, not a language for scientific analysis."""
from typing import Any, Literal

from pydantic import Field

from daw.models import Contract, Discovery, Evidence


class Profile(Contract):
    subject: str
    origin: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=1000)
    summary: str = Field(max_length=16000)
    level: int = Field(default=3, ge=0, le=3)
    facts: dict[str, Any] = Field(default_factory=dict)
    apparent_affordances: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class ObjectInput(Contract):
    blob: str
    role: str = "input"
    selector: dict[str, Any] = Field(default_factory=dict)
    source_identity: str = ""


class Derivation(Contract):
    inputs: list[ObjectInput] = Field(min_length=1)
    code: list[str] = Field(min_length=1)
    parameters: dict[str, Any]
    references: list[str]
    environment: dict[str, Any] = Field(min_length=1)
    # Exact invocation is part of reproducibility; this tool never executes it.
    command: list[str] = Field(default_factory=list)


class ArtifactRegistration(Contract):
    title: str = Field(min_length=1)
    summary: str = Field(max_length=16000)
    derivation: Derivation
    output_role: str = "result"
    kind: str = "file"
    limitations: list[str] = Field(default_factory=list)


class Seed(Contract):
    reference: str
    provider: str | None = None


class IndexPlan(Contract):
    seeds: list[Seed] = Field(default_factory=list)
    searches: list[Discovery] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)
    include_existing: bool = True
    level: int = Field(default=2, ge=0, le=3, description="Levels 0–2 drive completion; 3 retains v2 compatibility with optional enrichment")
    fetch_processed: bool = False
    extract_archives: bool = False
    max_tasks: int = Field(default=100, ge=1, le=100000)
    max_seconds: int = Field(default=300, ge=1)
    max_requests: int = Field(default=100, ge=1)
    max_download_bytes: int = Field(default=512 * 2**20, ge=1)
    max_asset_bytes: int = Field(default=64 * 2**20, ge=1)


class ResourceRef(Contract):
    kind: str
    provider: str
    native_id: str


class GraphRecord(ResourceRef):
    body: dict[str, Any] = Field(default_factory=dict)
    identifiers: dict[str, list[str]] = Field(default_factory=dict)
    relationships: list[dict[str, Any]] = Field(default_factory=list)


class Embedding(Contract):
    document_id: str
    fingerprint: str
    model: str = Field(min_length=1)
    vector: list[float] = Field(min_length=1, max_length=8192)


QuestionStatus = Literal["open", "completed", "paused"]
