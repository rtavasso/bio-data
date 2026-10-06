"""Read-only compact intake of inherited records; no measurements recomputed."""
import json
from pathlib import Path

question = Path(__file__).resolve().parents[1]
for name, key in [("investigations.json", "items"), ("discoveries.json", "candidates")]:
    record = json.loads((question / "outputs" / name).read_text())
    print(name, "revision", record["revision"])
    print(json.dumps({k: v for k, v in record.items() if k != key}, indent=2))
    for item in record[key]:
        fields = ["id", "status", "priority", "claim", "finding", "result", "limitation", "limitations", "next_action", "blocker_evidence", "artifacts", "validation_artifacts", "prediction_ref"]
        print(json.dumps({k: item[k] for k in fields if k in item}, indent=2))
record = json.loads((question / "outputs/mechanisms.json").read_text())
print("mechanisms.json metadata", json.dumps({k: v for k, v in record.items() if k not in ("nodes", "edges")}, indent=2))
print("Corrected mechanism edges")
for edge in record["edges"]:
    if any(word in json.dumps(edge).lower() for word in ["nae1", "antioxidant", "nrf2"]):
        print(json.dumps(edge, indent=2))
