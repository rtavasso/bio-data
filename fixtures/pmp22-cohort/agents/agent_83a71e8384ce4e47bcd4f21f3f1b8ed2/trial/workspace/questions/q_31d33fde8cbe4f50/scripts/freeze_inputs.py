"""Freeze selected immutable acquired inputs, plus inherited primary literature explicitly marked reuse."""

import json
from pathlib import Path
import subprocess

q = Path(__file__).resolve().parents[1]
s = q / "inputs/sources"
items = {}
for p in sorted(s.glob("*.receipt.json")):
    r = json.loads(p.read_text())
    if r.get("status") == 200 and "object" in r and "error" not in r:
        label = p.name.removesuffix(".receipt.json")
        items[label] = {
            "blob": r["sha256"],
            "url": r["url"],
            "receipt": str(p.relative_to(q)),
            "kind": "actual_new_http",
        }
        rr = subprocess.run(
            ["./bin/bio", "object", "add", str(p)], capture_output=True, text=True, check=True
        )
        items[label]["receipt_blob"] = json.loads(rr.stdout)["blob"]
for name in ["PMC2713384-bioc.source", "PMC10545524.source"]:
    p = q.parent / "q_a9976f21480c4fec" / "inputs/primary" / name
    if p.exists():
        r = subprocess.run(["./bin/bio", "object", "add", str(p)], capture_output=True, text=True, check=True)
        items["inherited-" + name] = {
            "blob": json.loads(r.stdout)["blob"],
            "kind": "inherited_source_bytes_not_new_retrieval",
        }
p = q / "outputs/predictions/mir29-retention-r001.json"
r = subprocess.run(["./bin/bio", "object", "add", str(p)], capture_output=True, text=True, check=True)
items["prediction"] = {"blob": json.loads(r.stdout)["blob"], "kind": "sealed_prediction"}
(q / "inputs/frozen-manifest-r001.json").write_text(json.dumps(items, indent=2))
print("FROZEN", len(items))
