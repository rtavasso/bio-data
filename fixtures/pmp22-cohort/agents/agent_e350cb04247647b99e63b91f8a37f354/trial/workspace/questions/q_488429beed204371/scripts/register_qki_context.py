"""Register verified source-text exports, preserving exact successful source bytes/receipts."""
import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]


def bio(*args):
    return json.loads(subprocess.run(["./bin/bio", *args], check=True, capture_output=True, text=True).stdout)


paths = sorted((q / "sources/qki-live").iterdir())
inputs = []
for path in paths:
    stored = bio("object", "add", str(path))
    assert stored["blob"] == hashlib.sha256(path.read_bytes()).hexdigest()
    inputs.append(stored["blob"])
receipt_path = q / "outputs/qki-extraction-r002.json"
receipt_blob = bio("object", "add", str(receipt_path))["blob"]
registered = {}
for filename, role in (("qki-reviewed-passages.txt", "qki-primary-source-passages"),
                       ("qki-refseq-records.txt", "qki-reference-transcript-labels")):
    path = q / "outputs" / filename
    args = ["register", str(path), "--question", q.name,
            "--title", "QKI/PMP22 bounded source audit: " + role,
            "--code", str(q / "scripts/extract_qki_context.py"),
            "--reference", receipt_blob, "--output-role", role,
            "--parameters", '{"analysis":"source-text extraction only; no paper-primer mapping or RNA reanalysis"}']
    for source in inputs:
        args.extend(["--input", source])
    result = bio(*args)
    (q / "outputs" / (filename + ".registration.json")).write_text(json.dumps(result, indent=2))
    artifact = bio("artifact", "show", result["artifact"])
    assert artifact["output_blob"] == hashlib.sha256(path.read_bytes()).hexdigest()
    (q / "outputs" / (filename + ".artifact.json")).write_text(json.dumps(artifact, indent=2))
    registered[filename] = result["artifact"]
(q / "outputs/qki-source-artifacts.json").write_text(json.dumps(registered, indent=2))
print(json.dumps(registered, indent=2))
