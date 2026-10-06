"""Advance the provenance checkpoint only; retain every scientific disposition."""
import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
o = q / "outputs"
current = o / "investigations.json"
record = json.loads(current.read_text())
assert record["revision"] == 30
assert record == json.loads((o / "investigations.r030.json").read_text())
prior_items = record["items"]
record["revision"] = 31
record["registration_manifest"] = {
    "artifact": "artifact_67f1a8f71cf2a4978144bdf321e65bd485c719476e2a0a4c281a61f319c1e3eb",
    "path": "outputs/upstream/final-registration-r002.json",
    "note": "r031 consolidation corrects the package pointer to the provenance-corrected r002 package; r030 preserved. Scientific items/statuses and feasible composition/state follow-up remain unchanged. See outputs/consolidation/REPORT.r001.md. No new biological investigation."
}
assert record["items"] == prior_items
text = json.dumps(record, indent=2, allow_nan=False) + "\n"
with (o / "investigations.r031.json").open("x") as stream:
    stream.write(text)
current.write_text(text)
print(json.dumps({"revision": 31, "scientific_items_unchanged": True, "prior_snapshot": "outputs/investigations.r030.json", "new_snapshot": "outputs/investigations.r031.json"}))
