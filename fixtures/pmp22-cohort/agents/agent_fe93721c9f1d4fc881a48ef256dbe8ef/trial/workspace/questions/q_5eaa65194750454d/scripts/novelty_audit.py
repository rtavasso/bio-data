"""Audit actual novelty-search records and peer locator artifact, without executing content."""
import hashlib
import json
import subprocess
from pathlib import Path
q=Path(__file__).resolve().parents[1]
records=[]
for label in ['nedd4','rnf40']:
    d=json.loads((q/f'outputs/novelty-{label}-discovery.json').read_text())
    for i,hit in enumerate(d['resources']):
        p=subprocess.run(['./bin/bio','data','show',hit],capture_output=True,text=True,check=True)
        (q/f'outputs/novelty-{label}-{i}.json').write_text(p.stdout)
        s=json.loads(p.stdout)['profiles'][0]['facts']['source_record']
        record={'query':label,**{k:s.get(k) for k in ['title','pmcid','doi','abstractText']}}
        records.append(record)
        print(json.dumps(record))
(q/'outputs/novelty-audit-records.json').write_text(json.dumps(records,indent=2)+'\n')
d=json.loads((q/'outputs/parent-locator-manifest.json').read_text())
h=d['output_blob']
p=q.parents[1]/'blobs/sha256'/h[:2]/h
assert hashlib.sha256(p.read_bytes()).hexdigest()==h
(q/'outputs/parent-locator-inspected.json').write_bytes(p.read_bytes())
print('PARENT_LOCATOR_VERIFIED',h)
print(p.read_text())
