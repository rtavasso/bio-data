"""Inspect two acquired FPKM tables, then acquire the complete metadata-selected TCam-2 set."""
import csv
import gzip
import json
import os
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]
w=Path(os.environ['BIO_WORKSPACE'])
o=q/'inputs/independent'
for asset in ['asset_969014698396e227503caf28f7e9d158','asset_02abf4e0f2e2f83681f73702f1dbe796']:
    rec=json.loads((o/(asset+'-fetch-r001.stdout')).read_text())
    sha=rec['blob']
    with gzip.open(w/'blobs/sha256'/sha[:2]/sha,'rt') as f:
        lines=list(csv.reader(f,delimiter='\t'))
    print('PROBE',asset,'ROWS',len(lines),'HEADER',lines[0],'FIRST',lines[1])
    print('TARGET',[r for r in lines[1:] if 'PMP22' in r])
files=json.loads((o/'GSE123016-files.json').read_text())['items']
selected=[f for f in files if f['name'].endswith('.txt.gz')]
assert len(selected)==21
manifest=[]
for f in selected:
    asset=f['asset_revision']
    old=o/(asset+'-fetch-r001.stdout')
    if old.exists():
        rec=json.loads(old.read_text())
    else:
        p=subprocess.run(['./bin/bio','fetch',asset,'--question',q.name],capture_output=True,text=True)
        old.write_text(p.stdout)
        (o/(asset+'-fetch-r001.stderr')).write_text(p.stderr)
        if p.returncode:
            print(p.stderr)
            p.check_returncode()
        rec=json.loads(p.stdout)
    assert rec['outcome']=='available_full'
    manifest.append(dict(f,acquisition=rec))
(o/'tcam-native-inputs.json').write_text(json.dumps(manifest,indent=2))
print('ACQUIRED',len(manifest),'PROCESSED FPKM FILES')
