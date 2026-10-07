"""Spec v2 V1: the agent-side claims_draft.py helper drafts claim entries from the agent's own registered tables."""
import json
import runpy
from pathlib import Path

from daw.artifacts import register_artifact
from daw.catalog import Workspace
from daw.commons import locators
from daw.community import Community
from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
from daw.work import create_question

HELPER = Path(__file__).parents[1] / ".agents/skills/bio-research/scripts/claims_draft.py"


def no_reserve(root):
    (root / "config.toml").write_text("[budgets]\nreserve_bytes=0\nreserve_fraction=0\n")


def resolve(catalog, pointer, output):
    """The value a drafted pointer names, read with the write-up checker's own locator code."""
    row = catalog.rows("SELECT output_blob FROM artifact WHERE id=?", (pointer["id"],))[0]
    data, _ = catalog.blob(row["output_blob"])
    locator = locators.parse_locator(pointer["locator"])
    if "row" in locator:
        header, rows = locators.read_table(data, output)
        return locators.cell(header, rows, locator)["value"]
    return locators.json_value(data, locator["key"])


def test_claims_draft_proposes_cell_pointers_from_own_tables_and_needs_the_authors_edit(tmp_path):
    """One entry per named row with artifact and `row=KEY;col=NAME` filled in; nothing is confirmed unedited."""
    root = tmp_path / "ws"
    Workspace.create(root).close()
    no_reserve(root)
    ws = Workspace(root)
    question = create_question(ws, "Contrasts")["question"]
    raw = tmp_path / "raw.tsv"
    raw.write_text("gene\tvalue\nPMP22\t2\n")
    imported = ws.local_asset(raw, "Synthetic input")
    code = ws.put_bytes(b"# saved analysis\n")

    def spec(title):
        return ArtifactRegistration(title=title, summary="fixture", derivation=Derivation(
            inputs=[ObjectInput(blob=imported["blob"], source_identity=imported["asset_revision"])], code=[code],
            parameters={"title": title}, references=[], environment={"fixture": True}))

    table = tmp_path / "contrasts.tsv"
    table.write_text("## comment line\ncontrast\tlog2 ratio\tp\tnote\nB vs A\t1.54\t0.003\tup\nC_vs_A\t-0.2\tNA\tflat\n"
                     "C_vs_A\t0.7\t0.04\trepeat key\n")
    contrast = register_artifact(ws, table, spec("Contrast table"), question=question)["artifact"]
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"n_samples": 12, "groups": {"A": {"mean": 0.5, "sd": 0.1}},
                                   "results": [{"name": "total RNA", "ratio": 0.56}], "label": "x"}))
    summarized = register_artifact(ws, summary, spec("Summary"), question=question)["artifact"]
    figure = tmp_path / "figure.png"
    figure.write_bytes(b"\x89PNG not a table")
    register_artifact(ws, figure, spec("Figure"), question=question)
    ws.close()
    helper = runpy.run_path(str(HELPER))
    document = helper["draft"](root, question)
    catalog = helper["Catalog"](root)
    first = next(c for c in document["claims"] if c["draft"]["row"] == "B vs A")
    assert first["text"].startswith("EDIT:") and "log2 ratio = 1.54; p = 0.003" in first["text"]
    assert [p["locator"] for p in first["pointers"]] == ["row=B%20vs%20A;col=log2%20ratio", "row=B%20vs%20A;col=p"]
    assert all(p["kind"] == "locator" and p["id"] == contrast for p in first["pointers"])
    # A repeated key is addressed by its data row; non-numeric cells (NA, note) get no pointer.
    repeated = [c for c in document["claims"] if c["draft"]["row"] == "C_vs_A"]
    assert [[p["locator"] for p in c["pointers"]] for c in repeated] == [["row=#2;col=log2%20ratio"],
                                                                        ["row=#3;col=log2%20ratio", "row=#3;col=p"]]
    keys = {p["locator"] for c in document["claims"] if c["draft"]["artifact"] == summarized for p in c["pointers"]}
    assert keys == {"key=n_samples", "key=groups.A.mean", "key=groups.A.sd", "key=results%5B0%5D.ratio"}
    # Every drafted pointer resolves, through the checker's locator code, to exactly the value the draft shows.
    for claim in document["claims"]:
        for pointer, cell in zip(claim["pointers"], claim["draft"]["cells"], strict=True):
            assert str(resolve(catalog, pointer, claim["draft"]["output"])).strip() == cell["value"]
    assert [s["reason"] for s in document["skipped"]] == ["not a TSV/CSV/JSON output (figure.png)"]
    # Confirmation refuses unedited entries; once the author rewrites one it emits a --claims list.
    path = tmp_path / "claims.draft.json"
    path.write_text(json.dumps(document))
    out = tmp_path / "claims.json"
    assert helper["main"](["confirm", str(path), "--out", str(out)]) == 2 and not out.exists()
    edited = {**document, "claims": [{**first, "text": "B is higher than A (log2 ratio 1.54, p 0.003).",
                                      "scope": {"context": "synthetic fixture", "direction": "higher in B"}}]}
    path.write_text(json.dumps(edited))
    assert helper["main"](["confirm", str(path), "--out", str(out)]) == 0
    claims = json.loads(out.read_text())
    assert claims == [{"text": "B is higher than A (log2 ratio 1.54, p 0.003).", "status": "supported",
                       "scope": {"context": "synthetic fixture", "direction": "higher in B"},
                       "pointers": first["pointers"]}]
    # The confirmed list publishes as ordinary claims; the helper itself never touches a board.
    board = Community.create(tmp_path / "community")
    try:
        no_reserve(board.library.root)
        board.library.close()
        board.library = Workspace(board.root / "library")
        post = board.publish("operator", "Contrast", "B over A.", workspace=root, artifacts=[contrast], claims=claims)
        assert len(post["claims"]) == 1 and "warnings" not in post
    finally:
        board.close()


def test_claims_draft_on_cohort_workspaces_resolves_every_cell(cohort):
    """On real data: drafts from three cohort agents' own registered outputs (copies, read-only); every proposed
    pointer resolves through the checker's locator code to the value shown, and the catalogs are unchanged."""
    helper = runpy.run_path(str(HELPER))
    proposed = 0
    for workspace in sorted(cohort.glob("agents/*/trial/workspace"))[:3]:
        before = (workspace / "catalog.sqlite").read_bytes()
        document = helper["draft"](workspace, max_rows=10)
        catalog = helper["Catalog"](workspace)
        for claim in document["claims"]:
            assert claim["text"].startswith("EDIT:") and claim["status"] == "supported"
            for pointer, cell in zip(claim["pointers"], claim["draft"]["cells"], strict=True):
                assert str(resolve(catalog, pointer, claim["draft"]["output"])).strip() == cell["value"]
        proposed += len(document["claims"])
        assert (workspace / "catalog.sqlite").read_bytes() == before
    assert proposed >= 50
