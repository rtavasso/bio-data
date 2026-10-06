"""Publish-ready interim registration for the already receipt-backed GTEx inspection."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
Q=Path(__file__).resolve().parents[1];ROOT=Q.parents[2]
def bio(*args):
    return json.loads(subprocess.run(['./bin/bio',*map(str,args)],cwd=ROOT,text=True,capture_output=True,check=True).stdout)
def store(p):
    r=bio('object','add',p);assert r['blob']==hashlib.sha256(p.read_bytes()).hexdigest();return r['blob']
recpath=Q/'outputs/inspection-execution-r001.json';rec=json.loads(recpath.read_text())
assert rec['exit_code']==0 and rec['complete'] and rec['code_unchanged']
code=Q/'scripts/inspect_native.py';assert store(code)==rec['code_sha256']
inputs=[]
for folder,pattern in [('inputs/native/v11-eqtl','*.gz'),('inputs/native/v11-sqtl','*.gz'),
                       ('inputs/native/v11-eqtl','*.parquet'),('inputs/native/v11-sqtl','*.parquet')]:
    for p in sorted((Q/folder).glob(pattern)):
        # Subcutaneous adipose/ovary selected pairs were acquired after this inspection and are not its inputs.
        if p.suffix=='.parquet' and not any(t in p.name for t in ['Nerve_Tibial','Cells_Cultured_fibroblasts']):continue
        inputs.append({'blob':store(p),'role':'source_evidence','selector':{'source_file':str(p.relative_to(Q))}})
for f in ['v11-eqtl-susie.tar','v11-eqtl-covariates.tar','v11-sqtl-groups.tar']:
    p=Q/'inputs/public'/f;inputs.append({'blob':store(p),'role':'source_evidence','selector':{'source_file':str(p.relative_to(Q))}})
out=Q/'outputs/inspection-v11.json'
assert next(x['sha256'] for x in rec['outputs'] if Path(x['path']).name==out.name)==hashlib.sha256(out.read_bytes()).hexdigest()
manifest={'title':'GTEx v11 PMP22 all-tested gene and splice-feature audit, preliminary native extraction',
 'summary':'Native rows across 50 eQTL and 48 sQTL contexts, sample/covariate counts and initial significant-only selections. Not independent replication or promoter initiation.',
 'kind':'file','output_role':'gtex_v11_native_inspection','derivation':{'inputs':inputs,'code':[rec['code_sha256']],
 'parameters':{'stage':'preliminary native extraction'},'references':[store(recpath)],'command':rec['argv'],
 'environment':{'python':platform.python_version(),'platform':platform.platform()}},
 'limitations':['Source q-values are tissue-specific. Annotation mapping and independent validation reported separately.',
                'No tested-negative claim from selected-only absence. No new LD/fine-mapping inference.']}
reg=Q/'outputs/registrations';reg.mkdir(exist_ok=True)
mp=reg/'inspection-v11.manifest.json';mp.write_text(json.dumps(manifest,indent=2))
r=bio('register',out,'--manifest',mp,'--question',Q.name)
(reg/'inspection-v11.registration.json').write_text(json.dumps(r,indent=2))
a=bio('artifact','show',r['artifact']);assert Path(a['path']).read_bytes()==out.read_bytes()
(reg/'inspection-v11.readback.json').write_text(json.dumps(a,indent=2))
print(r['artifact'])
