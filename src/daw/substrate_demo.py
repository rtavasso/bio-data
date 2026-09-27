"""An offline two-question example using ordinary code, not a scientific operator."""
import subprocess
import sys
from pathlib import Path

from daw.artifacts import attach_artifact, find_derivation, register_artifact
from daw.indexer import create_job, run_job
from daw.search import search
from daw.substrate_models import ArtifactRegistration, Derivation, IndexPlan, ObjectInput
from daw.util import environment_identity, write_json
from daw.work import create_question, record_event, sync_work

PREPARE = '''import csv, json, sys
with open(sys.argv[1], newline="") as stream:
    rows = list(csv.DictReader(stream, delimiter="\\t"))
# Preserve source strings, including literal identifiers and zeros.
with open(sys.argv[2], "w") as stream:
    json.dump(rows, stream, sort_keys=True)
'''


def demo(ws):
    fixtures = ws.root / "proposals" / "substrate-demo"
    fixtures.mkdir(parents=True, exist_ok=True)
    source = fixtures / "synthetic-unrelated-study.tsv"
    source.write_text("gene\tvalue\nPMP22\t0\nSOX10\t2\nNA\t3\n")
    imported = ws.local_asset(source, "synthetic-substrate-demo")
    job = create_job(ws, IndexPlan(scope=[imported["bundle"]]))
    indexed = run_job(ws, job["id"])
    first = create_question(ws, "Synthetic: recover PMP22 measurements from an unrelated study")
    second = create_question(ws, "Synthetic: reuse the same source representation for SOX10")
    qpath = Path(first["path"])
    script = qpath / "scripts" / "prepare.py"
    script.write_text(PREPARE)
    output = qpath / "outputs" / "literal-table.json"
    command = [sys.executable, str(script), str(ws.blob_path(imported["blob"])), str(output)]
    subprocess.run(command, check=True, timeout=ws.budgets.worker_seconds)
    record_event(ws, first["question"], "script_executed", {"command": command, "authorship": "trusted built-in synthetic demonstration", "returncode": 0})
    definition = ArtifactRegistration(title="Synthetic reusable whole source table", summary="Literal source strings; no biological inference",
        derivation=Derivation(inputs=[ObjectInput(blob=imported["blob"], source_identity=imported["asset_revision"])],
            code=[ws.put_file(script, "code")], parameters={"delimiter": "tab", "preserve": "all source strings"},
            references=[], environment=environment_identity(), command=["python", "prepare.py", "{input}", "{output}"]))
    registered = register_artifact(ws, output, definition, question=first["question"])
    reused = find_derivation(ws, definition.derivation)
    assert reused["state"] == "reusable"
    attach_artifact(ws, second["question"], registered["artifact"], name="literal-table.json")
    for question, feature in ((first, "PMP22"), (second, "SOX10")):
        path = Path(question["path"])
        (path / "LABBOOK.md").write_text(f"# Synthetic {feature} investigation\n\n"
            f"The source filename did not mention {feature}. Content search found it.\n\n"
            f"Reused artifact: {registered['artifact']}. It retains source strings, not normalized counts.\n\n"
            "No donor or promoter interpretation was inferred. This fixture is not biological evidence.\n")
        sync_work(ws, question["question"], summary=f"Synthetic {feature} content retrieval and reusable source table", status="completed")
    result = {"synthetic": True, "index": indexed["job"], "content_search": search(ws, feature="PMP22"),
        "artifact": registered, "reuse_state": reused["state"], "questions": [first, second],
        "next": "bio work show QUESTION_ID --notebook; bio artifact search --text reusable; bio provenance ARTIFACT_ID"}
    write_json(fixtures / "receipt.json", result)
    return result
