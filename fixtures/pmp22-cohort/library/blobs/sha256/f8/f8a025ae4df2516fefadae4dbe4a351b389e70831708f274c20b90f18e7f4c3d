"""Register correction products without replacing immutable r001 artifacts."""
import hashlib
import json
from pathlib import Path
import subprocess

Q = Path(__file__).resolve().parents[1]
OUT = Q/'outputs'
REV = OUT/'r002'
REG = REV/'registration'
REG.mkdir(exist_ok=True)


def cli(args):
    return json.loads(subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True).stdout)


def add(p):
    r=cli(['object','add',str(p),'--classification','reference'])
    assert r['blob']==hashlib.sha256(p.read_bytes()).hexdigest()
    return r['blob']


receipt=json.loads((OUT/'correction-execution-r002.json').read_text())
assert receipt['exit_code']==0 and receipt['complete'] and receipt['code_unchanged']
code=Q/'scripts/correct_delivery.py'
assert hashlib.sha256(code.read_bytes()).hexdigest()==receipt['code_sha256']
reference=add(OUT/'correction-execution-r002.json')
inputs=['artifact_85522f1b71c2bc1cac83ab83da224cc796de577f1cb3da1f93e0c00a14bf5992',
        'artifact_ebde69a87af5705390658ff9f9cdd643417ab50b7a9392852efed6c858f5eab1',
        'artifact_279ad27b9ff7707ed510c5da17c80b3145c4ac7488e4e2a0a2097bda07f831b7']
for p in [Q/'inputs/interpretation-curation.json',Q/'LABBOOK.md',OUT/'rna-named-gene-contrasts.tsv',
          OUT/'discovery-transporter-split.tsv',OUT/'registration/lipid-feedback-evidence.zip.json']:
    inputs.append(add(p))
for name in ['candidate-feedback-analysis.json','source-provenance.json','lipid-feedback-evidence.zip']:
    p=REV/name
    expected=next(x['sha256'] for x in receipt['outputs'] if Path(x['path']).name==name)
    assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
    args=['register',str(p),'--question',Q.name,'--title','Corrected PMP22 lipid-feedback: '+name,
          '--code',str(code),'--reference',reference,'--output-role','r002-'+name.replace('.','-'),
          '--parameters',json.dumps({'revision':'r002','scope':'correct narrative component transcription and uncertainty; quantitative results unchanged'})]
    for source in inputs:
        args+=['--input',source]
    r=cli(args)
    (REG/(name+'.json')).write_text(json.dumps(r,indent=2))
    check=cli(['artifact','show',r['artifact']])
    assert check['output_blob']==expected and not r['conflicting_outputs']
    (REG/(name+'.readback.json')).write_text(json.dumps(check,indent=2))
    print(name,r['artifact'])
