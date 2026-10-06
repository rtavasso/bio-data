"""Resolve newly source-located studies, preserving metadata receipts."""
import json
import subprocess
from pathlib import Path
q=Path(__file__).resolve().parents[1]

def cli(name,args):
    r=subprocess.run(['./bin/bio',*args],capture_output=True,text=True)
    (q/'outputs'/f'{name}.json').write_text(r.stdout)
    if r.returncode:
        print('FAILED',name,r.stdout,r.stderr)
        return None
    return json.loads(r.stdout)
for term in ['Nedd4','H2B','monoubiquitination']:
    d=cli('forum/search-'+term,['community','search','--text',term,'--limit','15'])
    print('FORUM',term,d)
for label in ['rnf40','figlia']:
    d=json.loads((q/f'outputs/{label}-discovery.json').read_text())
    for hit in d['resources']:
        s=cli(label+'-source',['data','show',hit])
        r=s['profiles'][0]['facts']['source_record']
        print(label,{k:r.get(k) for k in ['title','pmcid','doi','abstractText']})
        if r.get('pmcid'):
            a=cli(label+'-resolve',['resolve',r['pmcid'],'--provider','europepmc'])
            if a:
                b=cli(label+'-assets',['data','list','--scope',a['bundle'],'--limit','100'])
                print('ASSETS',label, b)
r=json.loads((q/'outputs/nedd4-geo-resolve.json').read_text())
print('NEDD_GEO_RESOLVE',r)
if r.get('bundle'):
    print('NEDD_GEO_ASSETS',cli('nedd4-geo-assets',['data','list','--scope',r['bundle'],'--limit','50']))
