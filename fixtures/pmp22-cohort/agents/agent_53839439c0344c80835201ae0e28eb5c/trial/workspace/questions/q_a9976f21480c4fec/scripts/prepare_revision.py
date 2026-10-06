"""Preserve corrected curation as a new immutable input version; keep prior provenance."""
import json
from pathlib import Path
import subprocess
q = Path(__file__).resolve().parents[1]
old = json.loads((q / 'inputs/analysis-manifest.json').read_text())
r = subprocess.run(['./bin/bio','object','add',str(q/'inputs/curation.json')],capture_output=True,text=True,check=True)
v = json.loads(r.stdout)
for item in old['objects']:
    if item['logical_path']=='inputs/curation.json':
        item.update(blob=v['blob'],bytes=v['bytes'])
old['revision_note']='r003: distinguish 6h array and 5h qPCR; withdraw unsupported browser/visual details; numeric measurements unchanged'
p = q/'inputs/analysis-manifest-r003.json'
assert not p.exists()
p.write_text(json.dumps(old,indent=2,allow_nan=False))
print(p)
