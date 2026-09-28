"""Strict public contracts. Unknown provider fields belong in raw snapshots."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class Budgets(Contract):
    # Zero disables research acquisition caps. Operational safeguards remain separate.
    asset_bytes: int = Field(default=0, ge=0)
    bundle_bytes: int = Field(default=0, ge=0)
    expanded_bytes: int = Field(default=4 * 2**30, gt=0)
    archive_members: int = Field(default=10000, gt=0)
    archive_depth: int = Field(default=3, ge=0)
    reserve_bytes: int = Field(default=5 * 2**30, ge=0)
    reserve_fraction: float = Field(default=0.1, ge=0, lt=1)
    requests: int = Field(default=0, ge=0)
    retries: int = Field(default=3, ge=1, le=6)
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    worker_seconds: int = Field(default=120, gt=0)
    worker_memory_bytes: int = Field(default=2 * 2**30, gt=0)
    preview_rows: int = Field(default=8, ge=1, le=100)
    max_rows: int = Field(default=1_000_000, gt=0)
    max_cells: int = Field(default=2_000_000, gt=0)


class Asset(Contract):
    native_id: str
    name: str
    url: str | None = None
    version: str | None = None
    size: int | None = Field(default=None, ge=0)
    checksum: str | None = None
    checksum_scope: str = "file"
    license: str = "unknown"
    selector: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: bool = False
    access: str = "listed"


class Page(Contract):
    items: list[dict[str, Any]]
    next_cursor: str | None
    exhausted: bool
    reported_total: int | None = None
    source_snapshot_id: str
    warnings: list[str] = Field(default_factory=list)


class Discovery(Contract):
    provider: Literal["europepmc", "zenodo", "chipatlas", "encode"]
    query: str
    max_pages: int = Field(default=3, ge=1, le=100)
    page_size: int = Field(default=25, ge=1, le=100)


class Evidence(Contract):
    blob: str
    locator: str
    method: str = "source_mapping"


class AssertionInput(Contract):
    subject: str
    field: str
    raw_value: Any
    value: Any
    evidence: Evidence
    alternatives: list[Any] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)


class Curation(Contract):
    asset_revision: str
    selector: dict[str, Any] = Field(default_factory=dict)
    kind: Literal["table", "interval", "signal", "matrix", "contact"]
    settings: dict[str, Any]
    assertions: dict[str, str] = Field(default_factory=dict)
    sample_map: dict[str, dict[str, str]] = Field(default_factory=dict)
    reference: str | None = None
    supersedes: str | None = None
    limitations: list[str] = Field(default_factory=list)


class Region(Contract):
    chrom: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    reference: str

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("region must be nonempty and half-open")
        return self


Operator = Literal[
    "table.feature_lookup", "contrast.published_lookup", "interval.overlap",
    "signal.interval_summary", "expression.feature_values", "expression.pseudobulk_counts",
    "contact.region_extract", "promoter.tss_summary",
]


class Query(Contract):
    question_id: str
    operator: Operator
    scope: list[str] = Field(default_factory=list)
    feature: str | None = None
    region: Region | None = None
    region2: Region | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    max_measurements: int = Field(default=100000, gt=0, le=2_000_000)

    @model_validator(mode="after")
    def required_target(self):
        if self.operator.startswith(("table.", "contrast.", "expression.")) and not self.feature:
            raise ValueError("this operator requires a literal feature identifier")
        if self.operator.startswith(("interval.", "signal.", "contact.")) and self.region is None:
            raise ValueError("this operator requires an explicit reference and region")
        allowed = {"required_resolution"} if self.operator == "contact.region_extract" else set()
        if set(self.parameters) - allowed:
            raise ValueError("unsupported operator parameters; no implicit analysis or normalization")
        resolution = self.parameters.get("required_resolution")
        if resolution is not None and (not isinstance(resolution, int) or isinstance(resolution, bool) or resolution < 1):
            raise ValueError("required_resolution must be a positive integer")
        return self


class Plan(Contract):
    action: Literal["acquire", "inspect", "extract"]
    assets: list[str]
    members: list[str] = Field(default_factory=list)
    # This enables acquisition only, never raw processing or downloaded code.
    allow_raw_download: bool = False
