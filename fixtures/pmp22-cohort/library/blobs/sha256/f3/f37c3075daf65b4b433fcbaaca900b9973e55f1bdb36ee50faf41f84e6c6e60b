"""Register the selective handoff and verify exact catalog bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
Q=Path(__file__).resolve().parents[1];ROOT=Q.parents[2]
REG=Q/'outputs/package-registration-r002';REG.mkdir(exist_ok=False)
def bio(*a):
    p=subprocess.run(['./bin/bio',*map(str,a)],cwd=ROOT,capture_output=True,text=True,check=True)
    return json.loads(p.stdout)
def store(p):
    b=bio('object','add',p)['blob'];assert hashlib.sha256(p.read_bytes()).hexdigest()==b;return b
def save(p,o):
    with p.open('x') as f:json.dump(o,f,indent=2)
recpath=Q/'outputs/package-execution-r002.json';rec=json.loads(recpath.read_text())
assert rec['exit_code']==0 and rec['complete'] and rec['code_unchanged']
assert store(Q/'scripts/package_handoff.py')==rec['code_sha256']
manifest=json.loads((Q/'outputs/handoff-manifest-r002.json').read_text())
inputs=[]
for r in manifest['members']:
    p=Q/r['path'];assert p.stat().st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
    inputs.append({'blob':store(p),'role':'package_member','selector':{'path':r['path']}})
registered=[]
for x in rec['outputs']:
    p=Path(x['path']);assert x['written'] and hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']
    m={'title':'PMP22 regulatory QTL selective handoff: '+p.name,'summary':'Byte-verified selective evidence, source/coordinate provenance, source estimates, independent tests, ranked follow-up and failure history. Not a complete raw-source closure or new analysis.',
       'kind':'file','output_role':p.name,'derivation':{'inputs':inputs,'code':[rec['code_sha256']],
       'parameters':{'scientific_rerun':False,'operation':'selective byte-preserving package'},
       'references':[store(recpath)],'command':rec['argv'],'environment':{'format':'zip/json','python':'3.12.8'}},
       'limitations':['Full cohort native sources and GTEx archives omitted from ZIP; registered scientific derivations retain their immutable blobs.']}
    mp=REG/(p.name+'.manifest.json');save(mp,m)
    r=bio('register',p,'--manifest',mp,'--question',Q.name);save(REG/(p.name+'.registration.json'),r)
    a=bio('artifact','show',r['artifact']);save(REG/(p.name+'.readback.json'),a)
    assert not r['conflicting_outputs'] and a['output_blob']==x['sha256'] and Path(a['path']).read_bytes()==p.read_bytes()
    registered.append({'file':p.name,'artifact':r['artifact']});print(json.dumps(registered[-1]),flush=True)
save(REG/'index.json',registered)
