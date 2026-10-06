"""Read-only JSON manifest summary; never executes inherited code."""
import json
import sys
from pathlib import Path

for arg in sys.argv[1:]:
    p = Path(arg)
    data = json.loads(p.read_text())
    print(f"\nFILE {p}\n")
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ("blobs", "artifacts", "receipts") and isinstance(value, list) and len(value) > 30:
                print(key, "entries", len(value))
            else:
                print(key, json.dumps(value, indent=2))
    else:
        print(json.dumps(data, indent=2))
