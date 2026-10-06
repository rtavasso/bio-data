"""Preserve local consolidation and register the actually executed integrity audit."""
import hashlib
import json
import subprocess
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
ROOT = W.parent
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


audit_path = C / "verification-r003.json"
audit = json.loads(audit_path.read_text())
execution = json.loads((C / "execution-r003.json").read_text())
assert execution["complete"] and execution["exit_code"] == 0
assert execution["code_sha256"] == sha(Q / "scripts/consolidation_verify.py")
for output in execution["outputs"]:
    # Restored paths are resolved by filename only within this known output directory.
    assert output["written"] and sha(C / Path(output["path"]).name) == output["sha256"]
assert audit["valid"] and audit["checks_passed"] == len(audit["checks"])
assert all(c["passed"] for c in audit["checks"])
inputs = set()
objects = {}
for relative, digest in audit["inputs"].items():
    path = W / relative
    assert sha(path) == digest, relative
    immutable = W / "blobs/sha256" / digest[:2] / digest
    if not immutable.exists():
        receipt = bio("object", "add", path)
        assert receipt["blob"] == digest
        objects[relative] = receipt
    inputs.add(digest)
# Retain prose as interpretation objects, not fake computed scientific artifacts.
for path in sorted(C.iterdir()):
    if path.is_file() and path.name != "preservation-r001.json":
        objects[str(path.relative_to(W))] = bio("object", "add", path)
for filename in ["investigations.r030.json", "investigations.r031.json", "discoveries.json", "mechanisms.json"]:
    path = Q / "outputs" / filename
    objects[str(path.relative_to(W))] = bio("object", "add", path)
# Exact catalog readback bytes used during the computation and its execution receipt.
for filename in ["artifact-readbacks-r003.json", "execution-r003.json"]:
    inputs.add(sha(C / filename))
save("preservation-r001.json", objects)
command = ["register", audit_path, "--question", Q.name,
           "--title", "PMP22 local consolidation: inherited evidence integrity and native-cell audit",
           "--summary", "Corrected source-context handoff; inherited rejection/untestable/exploratory distinctions retained. Provenance/numerical verification only, no new biological validation.",
           "--code", Q / "scripts/consolidation_verify.py",
           "--output-role", "consolidation-evidence-audit",
           "--parameters", json.dumps({"revision": 3, "offline": True, "scope": "integrity verification of inherited measurements", "execution_receipt": sha(C / "execution-r003.json")})]
for identifier in sorted(inputs | set(audit["artifact_ids"])):
    command += ["--input", identifier]
receipt = bio(*command)
save("registration-r001.json", receipt)
assert not receipt["conflicting_outputs"] and not receipt.get("warning"), receipt
readback = bio("artifact", "show", receipt["artifact"])
save("registration-readback-r001.json", readback)
assert readback["id"] == receipt["artifact"]
assert readback["output_blob"] == sha(audit_path) == receipt["output_blob"]
assert any(link["question_id"] == Q.name for link in readback["questions"])
print(json.dumps({"artifact": receipt["artifact"], "output_blob": receipt["output_blob"], "readback_verified": True, "conflicting_outputs": False, "preserved_objects": len(objects)}, indent=2))
