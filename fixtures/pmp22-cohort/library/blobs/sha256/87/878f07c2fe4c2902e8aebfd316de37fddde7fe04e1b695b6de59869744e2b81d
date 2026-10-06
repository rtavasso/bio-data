"""Register final synthesis and separate verification using exact producer receipts."""
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy
import openpyxl
import scipy

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
REG=OUT/'registrations-final'
REG.mkdir(exist_ok=True)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def cli(*args):
    return json.loads(subprocess.run(['./bin/bio',*map(str,args)],text=True,capture_output=True,check=True).stdout)

environment={'python':platform.python_version(),'numpy':numpy.__version__,'scipy':scipy.__version__,'openpyxl':openpyxl.__version__}
(OUT/'environment.json').write_text(json.dumps(environment,indent=2))
base=[json.loads(p.read_text())['artifact'] for p in sorted((OUT/'registrations').glob('*.json')) if '.readback.' not in p.name]
files=[ROOT/'inputs'/x for x in ['analysis-specification.json','interpretation-notes.json','frozen-acsl5-validation-prediction.json']]
for p in (ROOT/'inputs/public').glob('*.receipt.json'):
    files.append(p)
    r=json.loads(p.read_text())
    body=p.with_name(p.name.removesuffix('.receipt.json'))
    if r.get('complete_body'):
        assert sha(body)==r['sha256']
        files.append(body)
files += [ROOT/'inputs/community/parent-critique.json',ROOT/'inputs/community/translation-response.json',OUT/'immutable-input-manifest.json',OUT/'environment.json']
inputs=[]
manifest=[]
for path in dict.fromkeys(files):
    result=cli('object','add',path,'--classification','research-input')
    assert result['blob']==sha(path)
    inputs.append(result['blob'])
    manifest.append({'path':str(path.relative_to(ROOT)),'sha256':result['blob'],'bytes':path.stat().st_size})
(OUT/'final-input-manifest.json').write_text(json.dumps(manifest,indent=2))
# Registration order exposes the independent-checks artifact as a synthesis input.
for receipt_name in ['verification-execution-r001.json','synthesis-execution-r002.json']:
    path=OUT/receipt_name
    receipt=json.loads(path.read_text())
    assert receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged']
    assert sha(Path(receipt['producer']))==receipt['code_sha256']
    ref=cli('object','add',path,'--classification','execution-receipt')['blob']
    for output in receipt['outputs']:
        target=Path(output['path'])
        assert output['written'] and sha(target)==output['sha256']
        role=target.stem + ('-json' if target.name=='candidate-contrast-table.json' else '')
        regpath=REG/(role+'.json')
        if regpath.exists():
            reg=json.loads(regpath.read_text())
        else:
            cmd=['register',target,'--question',ROOT.name,'--title','Productive trafficking final: '+role,'--summary','Endpoint-specific quantitative synthesis, sensitivity and novelty/validation limits; no confirmed PMP22 rescue or independent ACSL5 protein-cargo validation.','--code',receipt['producer'],'--reference',ref,'--environment',OUT/'environment.json','--parameters',json.dumps({'receipt':receipt_name,'biological_replication':False,'code_inherited':False,'data_native':True}),'--output-role',role]
            for entry in dict.fromkeys(base+inputs):
                cmd += ['--input',entry]
            reg=cli(*cmd)
            regpath.write_text(json.dumps(reg,indent=2))
        back=cli('artifact','show',reg['artifact'])
        assert back['output_blob']==sha(target)
        assert any(q['question_id']==ROOT.name and q['relationship']=='produced' for q in back['questions'])
        (REG/(role+'.readback.json')).write_text(json.dumps(back,indent=2))
        print(role,reg['artifact'],'verified')
        if role=='independent-checks':
            base.append(reg['artifact'])
