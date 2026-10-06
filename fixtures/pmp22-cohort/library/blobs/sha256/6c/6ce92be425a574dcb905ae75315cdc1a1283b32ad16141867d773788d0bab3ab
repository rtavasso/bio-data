"""Acquire and inspect exact processed Nedd4 files, no raw sequencing."""
import gzip
import json
import subprocess
from pathlib import Path
q=Path(__file__).resolve().parents[1]
ws=q.parents[1]
a=json.loads((q/'outputs/nedd4-geo-assets.json').read_text())['items']
records=[]
for item in a:
    if not item['name'].endswith('.txt.gz'):
        continue
    r=subprocess.run(['./bin/bio','fetch',item['asset_revision'],'--question','q_5eaa65194750454d'],capture_output=True,text=True)
    (q/'outputs'/(item['name']+'-fetch.json')).write_text(r.stdout)
    assert r.returncode==0, r.stderr
    d=json.loads(r.stdout)
    records.append({'name':item['name'],'receipt':d})
    if not d.get('blob'):
        print('UNAVAILABLE',item['name'],d)
        continue
    p=ws/'blobs/sha256'/d['blob'][:2]/d['blob']
    with gzip.open(p,'rt') as f:
        print('NATIVE',item['name'], ''.join(next(f,'') for _ in range(4)))
(q/'outputs/nedd4-count-fetches.json').write_text(json.dumps(records,indent=2)+'\n')
