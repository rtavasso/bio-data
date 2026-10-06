"""Acquire selected primary documents/source-data through bio with real receipts."""
import json
import subprocess
import sys
from pathlib import Path
q = Path(__file__).resolve().parents[1]

def cli(name, args):
    r = subprocess.run(['./bin/bio', *args], capture_output=True, text=True)
    (q/'outputs'/f'{name}.json').write_text(r.stdout)
    if r.returncode:
        (q/'outputs'/f'{name}.stderr').write_text(r.stderr)
        print('FAILED', name, r.stdout, r.stderr)
        return None
    return json.loads(r.stdout)
for pmc in sys.argv[1:]:
    r = cli(pmc+'-resolve', ['resolve',pmc,'--provider','europepmc'])
    if not r:
        continue
    d = cli(pmc+'-assets',['data','list','--scope',r['bundle'],'--limit','100'])
    selected = [a for a in d['items'] if a['name'] == pmc+'.xml']
    if pmc == 'PMC10959528':
        selected = [a for a in d['items'] if a['name'] in ['elife-87394-fig4-data1.zip','elife-87394-fig3-data1.zip']]
    for a in selected:
        f = cli(a['name']+'-fetch',['fetch',a['asset_revision'],'--question','q_5eaa65194750454d'])
        print(pmc, a['name'], f)
