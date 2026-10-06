"""Preserve explicitly chosen audit inputs in this workspace's immutable object store."""
import json

from pathlib import Path
import subprocess
q = Path(__file__).resolve().parents[1]
out = q / 'inputs/analysis-manifest.json'
assert not out.exists()
curation = json.loads((q / 'inputs/curation.json').read_text())
paths = [q / 'inputs/curation.json']
for entry in curation['evidence']:
    stem = q / 'inputs/primary' / entry['source']
    options = [stem.with_suffix('.source'), stem.with_suffix('.xml')]
    paths.append(next(p for p in options if p.exists()))
paths += [q / 'inputs/primary/Hollien2009-full-pdf.source']
paths += sorted((q / 'inputs/primary').glob('*.receipt.json'))
paths += [q / 'inputs/primary/retrieval-r001.json']
paths += sorted((q / 'inputs/geo').glob('*.json'))
paths += [q / 'inputs/prior/mechanism-map.json']
rows = []
for p in paths:
    run = subprocess.run(['./bin/bio', 'object', 'add', str(p)], capture_output=True, text=True, check=True)
    value = json.loads(run.stdout)
    rows.append({'logical_path':str(p.relative_to(q)), 'blob':value['blob'], 'bytes':value['bytes']})
h = '78eeaf73be9d1576d1713c3a97b9988d386f713a21842f128eeb3f0a45f7d295'
rows.append({'logical_path':'inputs/native/GSM8792189.csv.gz','blob':h,'asset':'asset_47188fba5a4c009350afca180c0a45c4','bytes':1444956})
# Preserve exact fetched representation metadata, including actual native source receipt fields.
r = subprocess.run(['./bin/bio','data','show','asset_47188fba5a4c009350afca180c0a45c4'],capture_output=True,text=True,check=True)
p = q / 'inputs/geo/native-fetched.json'
p.write_text(r.stdout)
v = json.loads(subprocess.run(['./bin/bio','object','add',str(p)],capture_output=True,text=True,check=True).stdout)
rows.append({'logical_path':str(p.relative_to(q)),'blob':v['blob'],'bytes':v['bytes']})
out.write_text(json.dumps({'question':q.name,'objects':rows},indent=2,allow_nan=False))
print(json.dumps({'manifest':str(out),'objects':len(rows)}))
