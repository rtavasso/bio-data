"""Structural inspection of research artifacts; never biological graph scoring."""
import csv
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from daw.util import read_json

from .runner import safe_path


class ResearchRecord(BaseModel):
    model_config = ConfigDict(extra="allow")


class Evidence(ResearchRecord):
    source: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    basis: str = Field(min_length=1)


class Node(ResearchRecord):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    kind: str = Field(min_length=1)


class Edge(ResearchRecord):
    id: str = Field(min_length=1)
    source: str
    target: str
    mechanism: str = Field(min_length=1)
    context: str = Field(min_length=1)
    status: Literal["hypothesis", "supported", "contested", "rejected"]
    evidence: list[Evidence]

    @model_validator(mode="after")
    def evidence_for_attribution(self):
        if self.status != "hypothesis" and not self.evidence:
            raise ValueError("non-hypothesis edge needs attributed evidence; this does not verify the claim")
        return self


class Frontier(ResearchRecord):
    node: str
    question: str = Field(min_length=1)
    priority: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    status: Literal["open", "investigated", "deferred"]


class Change(ResearchRecord):
    reason: str = Field(min_length=1)
    evidence: list[Evidence]


class MechanismMap(ResearchRecord):
    revision: int = Field(ge=1, strict=True)
    scope: dict = Field(min_length=1)
    nodes: list[Node] = Field(min_length=1)
    edges: list[Edge] = Field(min_length=1)
    frontier: list[Frontier]
    changes: list[Change]

    @model_validator(mode="after")
    def consistent_identifiers(self):
        nodes, edges = {n.id for n in self.nodes}, {e.id for e in self.edges}
        if len(nodes) != len(self.nodes) or len(edges) != len(self.edges):
            raise ValueError("duplicate node or edge IDs")
        if any(e.source not in nodes or e.target not in nodes for e in self.edges):
            raise ValueError("edge references an unknown node")
        if any(f.node not in nodes for f in self.frontier):
            raise ValueError("frontier references an unknown node")
        return self


COVERAGE_FIELDS = ("edge_ids", "alternatives", "observation", "file_or_accession", "analysis", "inspection_status",
                   "source_locator", "result_or_limitation", "next_action")


def coverage_rows(path, graph):
    if path.stat().st_size > 4 * 2**20:
        raise ValueError("coverage artifact exceeds 4 MiB inspection budget")
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not set(COVERAGE_FIELDS) <= set(reader.fieldnames or []):
            raise ValueError("coverage columns missing")
        rows = list(reader)
    if not rows:
        raise ValueError("coverage has no rows")
    edge_ids = {e.id for e in graph.edges}
    for row in rows:
        if any(not isinstance(row.get(k), str) for k in COVERAGE_FIELDS):
            raise ValueError("incomplete coverage row")
        selected = {v.strip() for v in row["edge_ids"].split(";") if v.strip()}
        if not selected or not selected <= edge_ids:
            raise ValueError("coverage references unknown or empty edge IDs")
        if any(not row[k].strip() for k in ("alternatives", "observation", "analysis", "result_or_limitation", "next_action")):
            raise ValueError("coverage needs analysis, alternatives and limitations")
        status = row["inspection_status"]
        if status not in {"not_searched", "searched", "located", "inspected", "analyzed", "unavailable"}:
            raise ValueError("unknown coverage inspection status")
        if status in {"located", "inspected", "analyzed"} and not row["file_or_accession"].strip():
            raise ValueError("located/inspected/analyzed claims need source identity")
        if status in {"inspected", "analyzed"} and not row["source_locator"].strip():
            raise ValueError("inspection/analysis claims need evidence locator")
    return rows


def read_map(path):
    if path.stat().st_size > 4 * 2**20:
        raise ValueError("mechanism artifact exceeds 4 MiB inspection budget")
    return MechanismMap.model_validate(read_json(path))


def inspect_mechanisms(trial, questions):
    """Only inspect newly created questions; inherited artifacts earn no credit."""
    records = []
    for q in questions:
        entry = {"question": q["id"], "mechanism_map": False, "mechanism_revision": False, "evidence_coverage": False,
                 "errors": [], "evidence": []}
        folder = Path(q["path"]) / "outputs"
        try:
            current = safe_path(trial / "workspace", folder / "mechanisms.json")
            graph = read_map(current)
            entry.update(mechanism_map=True, revision=graph.revision)
            entry["evidence"].append("trial/workspace/" + str(folder / "mechanisms.json"))
        except (ValueError, OSError) as e:
            entry["errors"].append(str(e))
            records.append(entry)
            continue
        try:
            initial = read_map(safe_path(trial / "workspace", folder / "mechanisms.initial.json"))
            entry["mechanism_revision"] = graph.revision > initial.revision and bool(graph.changes)
            entry["evidence"].append("trial/workspace/" + str(folder / "mechanisms.initial.json"))
        except (ValueError, OSError) as e:
            entry["errors"].append(str(e))
        try:
            rows = coverage_rows(safe_path(trial / "workspace", folder / "evidence-coverage.tsv"), graph)
            entry.update(evidence_coverage=True, coverage_rows=len(rows))
            entry["evidence"].append("trial/workspace/" + str(folder / "evidence-coverage.tsv"))
        except (ValueError, OSError) as e:
            entry["errors"].append(str(e))
        records.append(entry)
    return records
