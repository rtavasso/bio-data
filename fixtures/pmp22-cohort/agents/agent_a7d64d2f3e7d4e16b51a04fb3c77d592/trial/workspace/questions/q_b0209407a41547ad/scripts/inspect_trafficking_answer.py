"""Inspect a peer endpoint artifact as static evidence; do not execute peer code."""
import csv
import hashlib
import json
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
meta = json.loads((OUT/'trafficking-peer-endpoint-artifact.json').read_text())
p = Path(meta['path'])
assert hashlib.sha256(p.read_bytes()).hexdigest() == meta['output_blob']
(OUT/'trafficking-peer-endpoint-manifest-readable.json').write_text(json.dumps(meta['manifest'],indent=2))
print('output',meta['manifest']['output'])
with p.open() as f:
    rows = list(csv.DictReader(f,delimiter='\t'))
selected = [r for r in rows if any(term in json.dumps(r).lower() for term in ['pmp22','abca1','endo'])]
result = {'artifact':meta['id'],'output_sha256_verified':meta['output_blob'],
          'inspection_only_not_reanalysis':True,'total_rows':len(rows),'selected_rows':selected}
(OUT/'trafficking-answer-evidence-inspection.json').write_text(json.dumps(result,indent=2,allow_nan=False))
print(json.dumps(result,indent=2))
post = json.loads((OUT/'trafficking-completed-analysis.json').read_text())
print('PEER ANALYSIS',post['content']['body'])
