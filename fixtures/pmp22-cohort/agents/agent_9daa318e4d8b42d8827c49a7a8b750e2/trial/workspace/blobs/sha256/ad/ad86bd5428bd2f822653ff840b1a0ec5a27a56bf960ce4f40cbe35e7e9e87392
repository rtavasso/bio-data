"""Sync and read back the exact consolidation handoff; no scientific edits."""
import hashlib
import json
import subprocess
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
ROOT = Q.parents[2]
C = Q / "outputs/consolidation"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def bio(*args):
    p = subprocess.run([str(ROOT / "bin/bio"), *map(str, args)], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def save(name, value):
    with (C / name).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


prior = json.loads((Q / "outputs/investigations.r030.json").read_text())
current = json.loads((Q / "outputs/investigations.json").read_text())
assert current["revision"] == 31 and prior["items"] == current["items"]
assert (Q / "outputs/investigations.json").read_bytes() == (Q / "outputs/investigations.r031.json").read_bytes()
check = subprocess.run([str(ROOT / "bin/python"), "-m", "daw.research_records", str(Q)], capture_output=True, text=True, check=True)
validation = json.loads(check.stdout)
assert validation["valid"] and not validation["errors"]
save("full-record-check-final.json", validation)
# Verify exact interpretation objects were preserved; old absolute receipt paths are ignored.
preserved = json.loads((C / "preservation-r001.json").read_text())
for name in ["REPORT.r001.md", "RETRIEVAL_POINTER.txt"]:
    path = C / name
    key = str(path.relative_to(Q.parents[1]))
    digest = preserved[key]["blob"]
    assert digest == sha(path)
    readback = bio("object", "show", digest)
    save(name + ".object-readback.json", readback)
summary = "PMP22 consolidated locally: corrected context-limited Nae1 rejection, untestable five-gene lock, exploratory reduced panel, inherited negatives/source limits and reusable broad data. Full records and native-cell/hash audit pass; native-memory write blocked by tool scope. Causal/state/human frontier remains open."
sync = bio("work", "sync", Q.name, "--summary", summary, "--status", "open")
save("sync-final.json", sync)
work = bio("work", "show", Q.name)
save("work-readback-final.json", work)
assert work["id"] == Q.name and work["status"] == "open"
assert work["current_work"] == sync["snapshot"] == "work_" + sync["blob"]
assert sync["files"]["LABBOOK.md"] == sha(Q / "LABBOOK.md")
report = {"question": Q.name, "snapshot": work["current_work"], "notebook_hash_verified": True,
          "scientific_queue_items_unchanged": True, "full_record_check_valid": True,
          "audit_artifact": "artifact_78fc412f0d9a4d6abdb740b28057e070257909b9fbd9456aedd01bca09e706b9",
          "native_memory_written": False, "reason": "Tool scope excludes task-specific research pointers; workspace/catalog fallback preserved. No learned skill created."}
save("handoff-final.json", report)
print(json.dumps(report, indent=2))
