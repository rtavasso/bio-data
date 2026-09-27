"""Rebuild schemas, source-reference index, and acceptance-test index."""
import ast
import re
from pathlib import Path

from daw.models import AssertionInput, Budgets, Curation, Discovery, Plan, Query
from daw.substrate_models import ArtifactRegistration, Derivation, Embedding, GraphRecord, IndexPlan, Profile
from daw.util import write_json

for model in (AssertionInput, Budgets, Curation, Discovery, Plan, Query, ArtifactRegistration, Derivation,
              Embedding, GraphRecord, IndexPlan, Profile):
    write_json(Path("contracts") / (model.__name__.lower() + ".schema.json"), model.model_json_schema())
tests = []
for path in sorted(Path("tests").rglob("test_*.py")):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            tests.append({"id": node.name, "path": str(path), "line": node.lineno, "network": "integration" in path.parts})
write_json("ACCEPTANCE_TESTS.json", {"origin": "Scientific safety from BUILD_SPEC section 18, v2 substrate/reuse, and v3 optional enrichment/retrieval evaluation", "tests": tests})
sources = []
for match in re.finditer(r"### (S\d+) — ([^\n]+)\n\n(https?://\S+)", Path("BUILD_SPEC.md").read_text()):
    sources.append({"id": match[1], "title": match[2], "url": match[3],
                    "status": "original documentation reference; live status in docs/receipts"})
write_json("SOURCES.json", {"origin": "Extracted from supplied BUILD_SPEC bibliography", "sources": sources})
