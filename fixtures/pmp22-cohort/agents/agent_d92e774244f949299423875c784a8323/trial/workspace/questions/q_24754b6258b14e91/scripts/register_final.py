"""Register final computed products with exact source/code/receipt lineage and readback."""
import hashlib
import json
from pathlib import Path
import subprocess
Q=Path(__file__).resolve().parents[1]
ROOT=Q.parents[2]
REG=Q/'outputs/registrations-final';REG.mkdir(exist_ok=True)
cache={}
def bio(*args):
    p=subprocess.run(['./bin/bio',*map(str,args)],cwd=ROOT,capture_output=True,text=True)
    if p.returncode:
        print(p.stdout,p.stderr);p.check_returncode()
    return json.loads(p.stdout)
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(2**22):h.update(b)
    return h.hexdigest()
def store(p):
    p=p.resolve()
    if p in cache:return cache[p]
    r=bio('object','add',p);assert r['blob']==sha(p);cache[p]=r['blob'];return r['blob']
def save(p,obj):
    with p.open('x') as f:json.dump(obj,f,indent=2,allow_nan=False)
recpath=Q/'outputs/final-execution-r002.json';rec=json.loads(recpath.read_text())
assert rec['complete'] and rec['exit_code']==0 and rec['code_unchanged']
assert store(Q/'scripts/harmonize_qtl.py')==rec['code_sha256']
inputs=[]
for x in json.loads((Q/'outputs/final-r002/input-manifest.json').read_text())['inputs']:
    p=Q/x['path'];assert sha(p)==x['sha256']
    inputs.append({'blob':store(p),'role':'analysis_input','selector':{'source_file':x['path']}})
# Full upstream native inputs and actual transport receipts remain retrievable.
for rel in ['inputs/public/QTD000100.complete.all.tsv.gz','inputs/public/QTD000100.complete.all.tsv.gz.receipt.json',
            'inputs/public/QTD000538.cc.tsv.gz','inputs/public/QTD000538.cc.tsv.gz.receipt.json',
            'inputs/public/README_eQTL_v11.txt','inputs/public/gtex-openfiles.json','inputs/public/catalogue-metadata-r7.tsv',
            'inputs/public/catalogue-methods.html','inputs/public/catalogue-columns.md','inputs/public/PMC8423625.xml',
            'inputs/public/PMC3673336.xml','inputs/public/PMC3100536-bioc.xml',
            'inputs/reused-cis/PMC3298281.html','inputs/reused-cis/PMC5181599.html',
            'outputs/predictions/fibroblast-cis-transfer-r001.json','outputs/predictions/adipose-first-exon-junction-transfer-r001.json']:
    inputs.append({'blob':store(Q/rel),'role':'source_evidence','selector':{'source_file':rel}})
old=json.loads((Q/'outputs/registrations/inspection-v11.manifest.json').read_text())
inputs.extend(old['derivation']['inputs'])
inputs=list({(x['blob'],json.dumps(x.get('selector',{}),sort_keys=True)):x for x in inputs}.values())
refs=[store(recpath)]
codes=[rec['code_sha256']]
for fn,code in [('inspection-execution-r001.json','inspect_native.py'),('independent-execution-r002.json','extract_independent.py')]:
    receipt=json.loads((Q/'outputs'/fn).read_text())
    assert receipt['exit_code']==0 and receipt['complete'] and receipt['code_unchanged']
    assert store(Q/'scripts'/code)==receipt['code_sha256']
    codes.append(receipt['code_sha256']);refs.append(store(Q/'outputs'/fn))
validation=json.loads((Q/'outputs/final-r002/analysis-validation.json').read_text())
common={'inputs':inputs,'code':codes,'references':refs,'command':rec['argv'],
        'parameters':{'revision':'r002','source_finemapping_reused':True,'new_LD_or_colocalization':False,
                      'inherited_artifact':'artifact_378dd1dde1005fd0e0d90e022df9e66367227636b3f092afd63a1abd31f6624a'},
        'environment':{k:validation[k] for k in ['python','platform','pyarrow']}}
registered=[]
for x in rec['outputs']:
    p=Path(x['path']);assert x['written'] and sha(p)==x['sha256']
    mp=REG/(p.name+'.manifest.json')
    manifest={'title':'Human PMP22 regulatory QTL audit: '+p.name,'kind':'file','output_role':p.name,
              'summary':'GTEx v11 coverage and source effects; GENCORD independent test; human interval/transcript mapping; no causal or promoter-initiation claim.',
              'derivation':common,'limitations':['GTEx exact all-tested variant IDs not retrieved; num_var/feature coverage retained.',
                 'Cross-tissue/release estimates not independent replication. TwinsUK exact junction not testable in retrieved export.',
                 'Source gene/splice q-values and SuSiE sets reused; no new genotype-level model.']}
    save(mp,manifest)
    r=bio('register',p,'--manifest',mp,'--question',Q.name)
    save(REG/(p.name+'.registration.json'),r)
    a=bio('artifact','show',r['artifact'])
    save(REG/(p.name+'.readback.json'),a)
    assert not r['conflicting_outputs'] and a['output_blob']==x['sha256']
    assert Path(a['path']).read_bytes()==p.read_bytes()
    registered.append({'file':p.name,'artifact':r['artifact'],'sha256':x['sha256']})
    print(json.dumps(registered[-1]),flush=True)
save(REG/'index.json',registered)
