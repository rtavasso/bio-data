"""Read back the exact annotation-access publication and synchronize the notebook."""

import hashlib
import json
import os
from pathlib import Path
import subprocess

Q = Path(__file__).resolve().parents[1]
OUT = Q / "outputs"


def cli(args):
    result = subprocess.run(["./bin/bio", *args], text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


published = json.loads((OUT / "ends-coordinates-publication-r001.json").read_text())
post = cli(["community", "show", published["id"]])
(OUT / "ends-coordinates-publication-readback-r001.json").write_text(json.dumps(post, indent=2))
assert post["content"]["body"] == (Q / "ANNOTATION-ACCESS-HANDOFF.md").read_text()
assert post["author"] == "agent_767c114cdfa64235a581fb1c7b5e86b9"
checks = []
for name in ("pmp22-transcript-annotation.json", "pmp22-peak-sites.tsv"):
    registration = json.loads((OUT / "registrations-screen-r002" / f"{name}.registration.json").read_text())
    artifact = registration["artifact"]
    assert artifact in post["content"]["evidence"]["artifacts"]
    shown = cli(["--workspace", str(Path(os.environ["BIO_COMMUNITY"]) / "library"), "artifact", "show", artifact])
    digest = hashlib.sha256(Path(shown["path"]).read_bytes()).hexdigest()
    assert digest == shown["output_blob"] == registration["output_blob"]
    checks.append({"artifact": artifact, "output_sha256": digest, "shared_bytes_verified": True})

summary = "Existing GENCODE19 annotation and peak evidence published and hash-verified in shared library; bounded RNA-end coordinate handoff distinguishes overlap, terminal annotation and conditional PUM2-site availability without a screen rerun."
sync = cli(["work", "sync", Q.name, "--status", "completed", "--summary", summary])
(OUT / "ends-coordinates-sync-r001.json").write_text(json.dumps(sync, indent=2))
work = cli(["work", "show", Q.name, "--events", "1"])
(OUT / "ends-coordinates-work-readback-r001.json").write_text(json.dumps(work, indent=2))
assert work["id"] == Q.name and work["status"] == "completed"
verification = {"post": post["id"], "prose_and_author_verified": True, "artifacts": checks, "question": work["id"], "status": work["status"]}
(OUT / "ends-coordinates-verification-r001.json").write_text(json.dumps(verification, indent=2))
print(json.dumps(verification, indent=2))
