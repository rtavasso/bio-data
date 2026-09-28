"""Small authored fixtures. Expected outcomes stay outside the subject prompt."""
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path

from daw.artifacts import register_artifact
from daw.catalog import Workspace
from daw.profiles import profile_asset, profile_manifest
from daw.substrate_models import ArtifactRegistration, Derivation, ObjectInput
from daw.util import environment_identity, write_json
from daw.work import create_question, sync_work

from .models import ResearchBudget

PREPARE = '''import csv, json, sys
with open(sys.argv[1], newline="") as f:
    rows = list(csv.DictReader(f, delimiter="\\t"))
with open(sys.argv[2], "w") as f:
    json.dump(rows, f, sort_keys=True)
'''


def catalog_snapshot(root):
    """Read without migration or holding a catalog connection during agent work."""
    path = Path(root) / "catalog.sqlite"
    if path.is_symlink():
        raise ValueError("catalog must not be a symlink")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        result = {table: [dict(r) for r in db.execute("SELECT * FROM " + table)] for table in
                  ("question", "work_snapshot", "work_event", "artifact", "question_artifact", "blob", "asset_revision")}
        result["integrity"] = db.execute("PRAGMA integrity_check").fetchone()[0]
    return result


def seed_mechanism_fixture(ws, inputs):
    """Fictional perturbations expose activity, RNA stability and a context decoy."""
    inputs.mkdir(exist_ok=True)
    tables = {
        "process-screen.tsv": (
            "condition\tR_abundance\tR_activity\tT_nascent_RNA\tT_RNA_half_life\tT_mature_RNA\n"
            "control\t1\t1\t1\t1\t1\nU_inhibited\t1\t0.4\t0.4\t1\t0.4\n"
            "D_inhibited\t1\t1\t1\t2\t2\n"),
        "other-context-screen.tsv": "condition\tR_activity\tT_mature_RNA\ncontrol\t1\t1\nX_inhibited\t0.1\t0.1\n"}
    identities = {}
    for name, content in tables.items():
        path = inputs / name
        path.write_text(content)
        imported = ws.local_asset(path, "synthetic-mechanism-exploration")
        profile_manifest(ws, imported["asset_revision"])
        profile_asset(ws, imported["asset_revision"])
        identities[name] = imported["asset_revision"]
    write_json(inputs / "source-context.json", {"synthetic": True, "target": "fictional gene T",
        "question_context": "fictional cell state C1", "prior_hypothesis": "R activity promotes T transcription; mechanism and upstream controls need investigation",
        "sources": identities, "assay_notes": {
            "process-screen.tsv": "State C1. Each column is a distinct synthetic assay, relative to its own control: R protein abundance, R activity reporter, T nascent RNA, T RNA half-life, T mature RNA. Values are not counts. U and D interventions have no selectivity or replication evidence supplied.",
            "other-context-screen.tsv": "State C2 only. Synthetic R activity and T mature RNA after X inhibition; no C1 evidence supplied."},
        "design_limits": "Illustrative summaries; no independent-donor count, uncertainty estimate or causal mediation test. Do not infer intervention specificity."})


def seed(root, kind, source_workspace=None, budget=None):
    root = Path(root)
    budget = budget or ResearchBudget()
    if source_workspace:
        source = Workspace(source_workspace)
        try:
            if sum(r["size"] for r in source.rows("SELECT size FROM blob")) > 2 * 2**30:
                raise ValueError("seed workspace exceeds the 2 GiB evaluation copy budget")
            with source.writer():
                source.backup(root)
        finally:
            source.close()
        # Backups intentionally omit disposable directories; recreate them before
        # handing the restored workspace to a researcher that will write objects.
        ws = Workspace.create(root)
    else:
        ws = Workspace.create(root)
    try:
        with ws.writer():
            # Empty question directories are not represented by backup files.
            for q in ws.rows("SELECT path FROM question"):
                folder = root / q["path"]
                if not folder.resolve().is_relative_to(root.resolve()) or folder.is_symlink():
                    raise ValueError("unsafe restored question path")
                for name in ("scripts", "outputs"):
                    child = folder / name
                    if child.is_symlink():
                        raise ValueError("unsafe restored question directory")
                    child.mkdir(parents=True, exist_ok=True)
            settings = tomllib.loads((root / "config.toml").read_text())["budgets"]
            settings.update(asset_bytes=budget.asset_bytes, bundle_bytes=budget.total_bytes, requests=budget.requests)
            (root / "config.toml").write_text("[budgets]\n" + "\n".join(f"{k} = {str(v).lower()}" for k, v in settings.items()) + "\n")
            if kind == "mechanism-blindspots":
                seed_mechanism_fixture(ws, root.parent / "inputs")
            elif kind != "empty":
                inputs = root.parent / "inputs"
                inputs.mkdir()
                path = inputs / "unrelated-selected-table.tsv"
                path.write_text("gene\tsample_A\tsample_B\nPMP22\t0\t5\nSOX10\t7\t11\n")
                imported = ws.local_asset(path, "synthetic-workflow-evaluation")
                profile_manifest(ws, imported["asset_revision"])
                profile_asset(ws, imported["asset_revision"])
                write_json(inputs / "source-context.json", {"synthetic": True,
                    "assay_scope": "gene-level expression table", "selection": "selected subset; complete measured feature universe not supplied",
                    "units": "unspecified", "sample_metadata": "sample labels only; donor identities and contrast direction not supplied",
                    "source": path.name, "asset_revision": imported["asset_revision"]})
                if kind == "artifact-reuse":
                    q = create_question(ws, "Previous preparation of the synthetic whole source table")
                    script = Path(q["path"]) / "scripts/prepare.py"
                    script.write_text(PREPARE)
                    output = Path(q["path"]) / "outputs/literal-table.json"
                    subprocess.run([sys.executable, str(script), str(path), str(output)], check=True, timeout=30)
                    register_artifact(ws, output, ArtifactRegistration(title="Prepared whole source expression table",
                        summary="All literal source cells in a reusable JSON representation; no normalization or interpretation",
                        derivation=Derivation(inputs=[ObjectInput(blob=imported["blob"], source_identity=imported["asset_revision"])],
                            code=[ws.put_file(script, "code")], parameters={"delimiter": "tab", "preserve": "source strings"},
                            references=[], environment=environment_identity(), command=["python", "prepare.py", "{input}", "{output}"])), question=q["question"])
                    (Path(q["path"]) / "LABBOOK.md").write_text("# Previous preparation\n\nPreserved the whole synthetic source table as literal JSON rows; no normalization, donor or promoter inference.\n")
                    sync_work(ws, q["question"], summary="Prepared reusable whole source table", status="completed")
    finally:
        ws.close()
    return catalog_snapshot(root)
