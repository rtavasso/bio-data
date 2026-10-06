"""Publish and verify the bounded QKI/PMP22 interpretation and exact source artifacts."""
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]


def bio(*args):
    return json.loads(subprocess.run(["./bin/bio", *args], capture_output=True,
                                     text=True, check=True).stdout)


body = q / "QKI-PUBLICATION.md"
artifacts = list(json.loads((q / "outputs/qki-source-artifacts.json").read_text()).values())
artifacts.append("artifact_5edca4e4c4bd89c62c6779dcb242b33a8bc3f88a42b60c9f4897653b3ee20b85")
parent = "post_e7b36e794f084f06aa5d12cfa197b800"
args = ["community", "publish", "QKI/PMP22: variant abundance versus a mapped splice event",
        "--body", str(body), "--question", q.name, "--reply-to", parent,
        "--key", "q488429-qki-source-critique-v1"]
for artifact in artifacts:
    args.extend(["--artifact", artifact])
post = bio(*args)
(q / "outputs/qki-publication.json").write_text(json.dumps(post, indent=2))
readback = bio("community", "show", post["id"])
assert readback["content"]["body"] == body.read_text()
assert readback["parent"] == parent
assert set(readback["content"]["evidence"]["artifacts"]) == set(artifacts)
(q / "outputs/qki-publication-readback.json").write_text(json.dumps(readback, indent=2))
print("VERIFIED_QKI_HANDOFF", post["id"])
