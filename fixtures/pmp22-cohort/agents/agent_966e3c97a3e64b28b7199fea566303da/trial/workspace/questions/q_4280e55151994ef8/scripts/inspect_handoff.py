"""Resolve selected peer evidence without executing its code or repeating its analysis."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'inputs'/'community'
results = []
for label in ['manifest','samples','original-footprint','original-summary']:
    artifact = json.loads((DEST/f'handoff-{label}-artifact.json').read_text())
    blob = artifact['output_blob']
    proc = subprocess.run(['./bin/bio','--workspace',str(Path(os.environ['BIO_COMMUNITY'])/'library'),'object','show',blob],text=True,capture_output=True,check=True)
    obj = json.loads(proc.stdout)
    data = Path(obj['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == blob
    if label == 'original-footprint':
        (DEST/f'handoff-{label}.tsv').write_bytes(data)
    else:
        (DEST/f'handoff-{label}.json').write_text(json.dumps(json.loads(data),indent=2,allow_nan=False)+'\n')
    results.append({'label':label,'artifact':artifact['id'],'blob':blob,'bytes':len(data),'hash_verified':True})
(DEST/'handoff-readback-validation.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
print(json.dumps(results,indent=2))
