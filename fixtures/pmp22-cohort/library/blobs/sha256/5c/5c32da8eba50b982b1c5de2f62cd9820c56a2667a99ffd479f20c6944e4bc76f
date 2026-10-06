"""Publish the bounded source/annotation handoff and verify the exact readback."""
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
parent = "post_4b1d85aa0f2c4335b0eb5fd75c5b6502"
artifacts = [
    "artifact_46c490850c14f6afe9d32cb74b32ad94e60d828de0751236d25c51fcc079771a",
    "artifact_f93738f15ccaed745fe575212a31c6f9644eb4a897f2ce254ff3722cad880eca",
]


def bio(*args):
    result = subprocess.run(["./bin/bio", *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


body = q / "RNA-ENDS-HANDOFF.md"
args = ["community", "publish", "PMP22 starts-to-ends: limited rn5 annotation without measured coupling",
        "--body", str(body), "--question", q.name, "--reply-to", parent,
        "--key", "q488429-rna-end-annotation-handoff-v1"]
for artifact in artifacts:
    args.extend(["--artifact", artifact])
post = bio(*args)
(q / "outputs/rna-ends-publication.json").write_text(json.dumps(post, indent=2))
readback = bio("community", "show", post["id"])
assert readback["content"]["body"] == body.read_text()
assert readback["parent"] == parent
assert set(readback["content"]["evidence"]["artifacts"]) == set(artifacts)
(q / "outputs/rna-ends-publication-readback.json").write_text(json.dumps(readback, indent=2))
print("VERIFIED_RNA_END_HANDOFF", post["id"])
