"""Spec v3 G8: the status table in docs/COLLOQUY.md states demo, cohort and live checks separately, and every
cohort or live claim it makes is backed: a cohort cell names tests that exist and use the committed real-data
fixture, a live cell names receipts that exist under docs/v3/receipts/. Offline; reads files only."""
import ast
import re
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "COLLOQUY.md"
HEADER = ["Item", "Status", "Demo", "Cohort fixture", "Live", "Code and notes"]
PREFIXES = ("yes", "partly", "no", "n/a")
MODULE_STATUSES = {"implemented", "implemented; limitation", "implemented, offline only"}
V3_STATUSES = {"met", "met offline", "partly", "not met", "off"}
V3_ITEMS = [f"B{n}" for n in range(1, 17)] + [f"G{n}" for n in range(1, 9)] + [f"V{n}" for n in range(11, 19)]
TEST_REF = re.compile(r"(tests/[\w/]+\.py)::(\w+)")
RECEIPT_REF = re.compile(r"docs/v3/receipts/[\w.-]+")
COHORT_FIXTURES = {"cohort", "cohort_copy"}


def split_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def status_rows(text=None):
    """Every row of every table under the status section whose header is HEADER: {item: {column: cell}}."""
    text = text if text is not None else DOC.read_text()
    section = text.split("## Status per specification item", 1)[1].split("\n## ", 1)[0]
    rows, columns = {}, None
    for line in section.splitlines():
        if not line.startswith("|"):
            columns = None
            continue
        cells = split_row(line)
        if columns is None:
            columns = cells
            continue
        if set(line) <= set("|-: "):
            continue
        if columns == HEADER:
            assert len(cells) == len(HEADER), f"{cells[0]}: {len(cells)} cells, expected {len(HEADER)}"
            assert cells[0] not in rows, f"duplicate row {cells[0]}"
            rows[cells[0]] = dict(zip(HEADER, cells, strict=True))
    return rows


@cache
def _module(path):
    source = (ROOT / path).read_text()
    return source, ast.parse(source)


def _names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def uses_cohort(path, name):
    """True when the test function exists and uses the committed cohort fixture: a `cohort`/`cohort_copy`
    argument, a fixture of the same module or conftest built on them, or the fixture path (directly or through
    a module-level constant)."""
    source, tree = _module(path)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert name in functions, f"{path}::{name} does not exist"
    conftest_source, conftest = _module("tests/conftest.py")
    fixtures = {n.name: n for t in (conftest, tree) for n in t.body if isinstance(n, ast.FunctionDef)
                and any("fixture" in ast.unparse(d) for d in n.decorator_list)}
    constants = {t.id for n in tree.body if isinstance(n, ast.Assign) and "pmp22-cohort" in ast.unparse(n.value)
                 for t in n.targets if isinstance(t, ast.Name)}

    def cohort_like(function, seen=()):
        text = ast.unparse(function)
        if ("fixtures" in text and "pmp22-cohort" in text) or _names(function) & constants:
            return True
        for arg in (a.arg for a in function.args.args):
            if arg in COHORT_FIXTURES:
                return True
            if arg in fixtures and arg not in seen and cohort_like(fixtures[arg], (*seen, arg)):
                return True
        return False
    return cohort_like(functions[name])


def test_status_table_cells_are_backed_by_tests_and_receipts():
    rows = status_rows()
    assert len(rows) >= 75  # 45 module rows and 32 v3 items
    # Every v3 item has its own row with an honest v3 status; modules keep the module vocabulary.
    for item in V3_ITEMS:
        matching = [key for key in rows if key.split(" ", 1)[0] == item]
        assert matching, f"no status row for {item}"
    for key, row in rows.items():
        v3 = key.split(" ", 1)[0] in V3_ITEMS
        assert row["Status"] in (V3_STATUSES if v3 else MODULE_STATUSES), (key, row["Status"])
        for column in ("Demo", "Cohort fixture", "Live"):
            assert row[column].startswith(PREFIXES), f"{key}: {column} must start with yes, partly, no or n/a"
        # Every named test exists, whatever the column.
        for cell in row.values():
            for path, name in TEST_REF.findall(cell):
                assert (ROOT / path).is_file(), f"{key}: {path} does not exist"
                source, tree = _module(path)
                assert name in {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}, f"{key}: {path}::{name}"
        # A cohort claim names cohort tests, each of which uses the cohort fixture.
        cohort = row["Cohort fixture"]
        if cohort.startswith(("yes", "partly")):
            refs = TEST_REF.findall(cohort)
            assert refs, f"{key}: the cohort cell claims a check but names no test"
            for path, name in refs:
                assert uses_cohort(path, name), f"{key}: {path}::{name} does not use the cohort fixture"
        # A live claim names receipts that exist; a live receipt is never claimed in another column.
        live = row["Live"]
        if live.startswith(("yes", "partly")):
            receipts = RECEIPT_REF.findall(live)
            assert receipts, f"{key}: the live cell claims a run but names no receipt"
            for receipt in receipts:
                assert (ROOT / receipt).is_file(), f"{key}: {receipt} does not exist"
        if row["Demo"].startswith(("yes", "partly")):
            assert TEST_REF.findall(row["Demo"]) or "e2e" in row["Demo"], f"{key}: the demo cell names no test"
        # Notes do not smuggle a cohort or live claim past the cells.
        notes = row["Code and notes"]
        assert not re.search(r"checked on (the|a) cohort", notes, re.IGNORECASE), f"{key}: claim in notes"
        assert not RECEIPT_REF.search(notes), f"{key}: a receipt belongs in the Live cell"


def test_unmet_v3_items_say_so_plainly():
    rows = {key.split(" ", 1)[0]: row for key, row in status_rows().items()}
    for item in ("G4", "V17"):
        assert rows[item]["Status"] == "not met" and rows[item]["Live"].startswith("no")
    assert rows["V18"]["Status"] == "off" and "Stays off" in rows["V18"]["Code and notes"]
    assert rows["G2"]["Status"] == "partly" and "not met" in rows["G2"]["Code and notes"]
    assert rows["V15"]["Live"].startswith("no") and "not deployed" in rows["V15"]["Live"]
    assert rows["V16"]["Status"] == "partly" and "no claim citation on the cohort" in rows["V16"]["Code and notes"]


def test_the_parser_rejects_unbacked_claims(tmp_path):
    """The checks above fail on a row that claims a cohort or live check it cannot back."""
    good = "| B1 x | met | yes: e2e | yes: `tests/test_commons_moderation.py::test_every_get_route_taking_a_post_id_serves_the_stub_cohort` | n/a | x |"
    table = "## Status per specification item\n\n| " + " | ".join(HEADER) + " |\n|---|---|---|---|---|---|\n"
    assert status_rows(table + good + "\n")["B1 x"]["Status"] == "met"
    assert uses_cohort("tests/test_commons_moderation.py", "test_every_get_route_taking_a_post_id_serves_the_stub_cohort")
    assert uses_cohort("tests/test_commons_records.py", "test_cohort_graph_store_build_update_and_per_node_latency")
    assert not uses_cohort("tests/test_commons_moderation.py", "test_every_get_route_taking_a_post_id_serves_the_stub_demo")
    with pytest.raises(AssertionError, match="does not exist"):
        uses_cohort("tests/test_commons_moderation.py", "test_no_such_test")
    with pytest.raises(AssertionError, match="cells"):
        status_rows(table + "| B1 x | met | yes |\n")
