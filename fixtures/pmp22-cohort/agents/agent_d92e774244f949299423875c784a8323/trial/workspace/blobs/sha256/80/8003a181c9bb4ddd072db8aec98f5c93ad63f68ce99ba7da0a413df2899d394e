import hashlib
import json
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
for r in json.loads((Q/'outputs/handoff-manifest.json').read_text())['members']:
    p=Q/r['path']
    if p.stat().st_size!=r['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:
        print('CHANGED AFTER PACKAGE',r['path'],'packaged_bytes',r['bytes'],'current_bytes',p.stat().st_size)
