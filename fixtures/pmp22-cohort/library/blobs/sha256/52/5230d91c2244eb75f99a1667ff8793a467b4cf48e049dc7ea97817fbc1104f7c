"""Fetch explicitly selected processed per-sample inventory entries, no raw files."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

R=Path(__file__).resolve().parents[1]
inventory=json.loads((R/'outputs'/sys.argv[1]).read_text())
selected=[a for a in inventory['items'] if a['name'].startswith('GSM') and a['name'].endswith('.txt.gz')]
assert selected
manifest=[]
for a in selected:
    name=a['name'].split('_')[0]
    receipt=R/'outputs'/('fetch-'+name+'.json')
    if receipt.exists():
        info=json.loads(receipt.read_text())
    else:
        p=subprocess.run(['./bin/bio','fetch',a['asset_revision'],'--question','q_7e888aba063b4092'],text=True,capture_output=True,check=True)
        info=json.loads(p.stdout)
        receipt.write_text(json.dumps(info,indent=2)+'\n')
    blob=info['blob']
    obj=json.loads(subprocess.run(['./bin/bio','object','show',blob],text=True,capture_output=True,check=True).stdout)
    src=Path(obj['path'])
    assert hashlib.sha256(src.read_bytes()).hexdigest()==blob
    dest=R/'inputs'/'sources'/name
    if not dest.exists():
        shutil.copyfile(src,dest)
    assert hashlib.sha256(dest.read_bytes()).hexdigest()==blob
    manifest.append({'source_name':a['name'],'sample':name,'asset':info['asset_revision'],'blob':blob,'bytes':dest.stat().st_size})
    print(name,blob)
(R/'outputs'/'GSE65778-fetch-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
