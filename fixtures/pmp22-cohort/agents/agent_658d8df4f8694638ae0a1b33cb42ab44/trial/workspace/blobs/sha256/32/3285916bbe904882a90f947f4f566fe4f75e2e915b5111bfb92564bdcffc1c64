"""Preserve input provenance and register only outputs backed by the completed producing receipt."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs'
REG = OUT/'registrations'
REG.mkdir(exist_ok=True)

def cli(*args):
    return json.loads(subprocess.run(['./bin/bio', *map(str,args)], capture_output=True, text=True, check=True).stdout)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

receipt_path=OUT/'execution-r002.json'
receipt=json.loads(receipt_path.read_text())
assert receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged']
assert digest(Path(receipt['producer']))==receipt['code_sha256']
validation=json.loads((OUT/'analysis-validation.json').read_text())
assert validation['valid'] and all(x['passed'] for x in validation['checks'])
inputs=[]
files=[ROOT/'inputs/public'/name for name in validation['input_hashes']]
files += [ROOT/'inputs/analysis-specification.json']
files += [ROOT/'inputs/public'/name for name in ['JCI201297.html','JCI201297-supplement-native.pdf','PMC6979480.xml','PMC7771966.xml','CAM40408.html','PMC7771966-supplements.zip','UGGT-extraction.json']]
files += list((ROOT/'inputs/public').glob('*.receipt.json'))
manifest=[]
for path in dict.fromkeys(files):
    obj=cli('object','add',path,'--classification','research-input')
    assert obj['blob']==digest(path)
    inputs.append(obj['blob'])
    manifest.append({'path':str(path.relative_to(ROOT)),'sha256':obj['blob'],'bytes':path.stat().st_size})
(OUT/'immutable-input-manifest.json').write_text(json.dumps(manifest,indent=2))
ref=cli('object','add',receipt_path,'--classification','execution-receipt')['blob']
for output in receipt['outputs']:
    path=Path(output['path'])
    assert output['written'] and digest(path)==output['sha256']
    role=path.stem
    regpath=REG/(role+'.json')
    if regpath.exists():
        result=json.loads(regpath.read_text())
    else:
        args=['register',path,'--question',ROOT.name,'--title','Productive trafficking: '+role,'--summary','Executed native endpoint contrasts for PMP22 counter-screen, independent HRP cargo screen and IGF1R maturation; descriptive/selection and transfer limitations retained.','--code',ROOT/'scripts/analyze_cargo.py','--reference',ref,'--output-role',role,'--parameters',json.dumps({'analysis':'native cargo contrasts','biological_replication':False,'receipt':'execution-r002.json','formulas_executed':False})]
        for blob in dict.fromkeys(inputs):
            args.extend(['--input',blob])
        result=cli(*args)
        regpath.write_text(json.dumps(result,indent=2))
    back=cli('artifact','show',result['artifact'])
    assert back['output_blob']==digest(path)
    assert any(q['question_id']==ROOT.name and q['relationship']=='produced' for q in back['questions'])
    (REG/(role+'.readback.json')).write_text(json.dumps(back,indent=2))
    print(role,result['artifact'],'verified')
