"""Acquire exact selected processed reference files, preserving every CLI receipt."""
from pathlib import Path
import json
import subprocess

Q = Path(__file__).resolve().parents[1]
I = Q / 'inputs'
R = I / 'managed'
R.mkdir(exist_ok=True)
selected = []
for name in ['inventory-SNAT-paper.json', 'inventory-GSE138577.json']:
    d = json.loads((I/name).read_text())
    for row in d['items']:
        if row['name'] in ['elife-58591-supp1.xls','elife-58591-supp2.xls'] or ('10X_P1_' in row['name'] and row['name'].endswith('.gz')):
            selected.append(row)
for row in selected:
    name = row['name']
    rp = R/(name+'.fetch.json')
    if rp.exists():
        print('EXISTING',name)
        continue
    p = subprocess.run(['./bin/bio','fetch',row['asset_revision'],'--question',Q.name], text=True, capture_output=True)
    (R/(name+'.stderr')).write_text(p.stderr)
    if p.returncode:
        (R/(name+'.failed.json')).write_text(p.stdout)
        print('FAILED',name,p.stdout[-1000:],p.stderr[-1000:])
        continue
    d=json.loads(p.stdout)
    rp.write_text(json.dumps(d,indent=2))
    print('FETCH',name,json.dumps(d),flush=True)
    asset=d.get('asset_revision') or d.get('asset')
    if asset:
        r=subprocess.run(['./bin/bio','inspect',asset],text=True,capture_output=True)
        (R/(name+'.inspect.json')).write_text(r.stdout)
        (R/(name+'.inspect.stderr')).write_text(r.stderr)
(Q/'outputs/selected-reference-assets.json').write_text(json.dumps(selected,indent=2))
