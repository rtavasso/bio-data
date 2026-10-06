"""Register verified products with real producer receipt and verify exact readback."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
REG=OUT/'registrations'
REG.mkdir(exist_ok=True)
QUESTION='q_cfe0be2ab0e146a4'
PRODUCTS=[('disposition-evidence.tsv','disposition-evidence'),('assay-eligibility.json','assay-eligibility'),('coip-selected-native.tsv','coip-selected-native'),('coip-audit.json','coip-universe-audit'),('rer1-discriminating-test.json','rer1-discriminating-test'),('source-locators.json','source-locators'),('validation.json','validation')]
parser=argparse.ArgumentParser()
parser.add_argument('stage',choices=['first','remaining'])
args=parser.parse_args()

def cli(*cmd):
    return json.loads(subprocess.run(['./bin/bio',*cmd],check=True,capture_output=True,text=True).stdout)

receipt=json.loads((OUT/'execution-r001.json').read_text())
assert receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged']
assert hashlib.sha256(Path(receipt['producer']).read_bytes()).hexdigest()==receipt['code_sha256']
for output in receipt['outputs']:
    assert output['written'] and hashlib.sha256(Path(output['path']).read_bytes()).hexdigest()==output['sha256']
validation=json.loads((OUT/'validation.json').read_text())
assert validation['valid'] and all(x['passed'] for x in validation['checks'])
ref=cli('object','add',str(OUT/'execution-r001.json'),'--classification','execution-receipt')
(REG/'producer-object.json').write_text(json.dumps(ref,indent=2))
inputs=list(dict.fromkeys(validation['used_input_blobs'].values()))
for name,role in (PRODUCTS[:1] if args.stage=='first' else PRODUCTS[1:]):
    regpath=REG/(role+'.json')
    if regpath.exists():
        result=json.loads(regpath.read_text())
    else:
        cmd=['register',str(OUT/name),'--question',QUESTION,'--title','PMP22 disposition audit: '+role,
             '--summary','Primary-source endpoint audit and native selected co-IP eligibility; no independent biological replication or functional rescue established.',
             '--code',str(ROOT/'scripts/audit_disposition.py'),'--reference',ref['blob'],
             '--parameters',json.dumps({'analysis':'validated agent-curated endpoint evidence and native scalar audit','scope':'two primary trafficking papers plus export/peer applicability','biological_replication':False}),
             '--output-role',role]
        for blob in inputs:
            cmd+=['--input',blob]
        result=cli(*cmd)
        regpath.write_text(json.dumps(result,indent=2))
    assert result['output_blob']==hashlib.sha256((OUT/name).read_bytes()).hexdigest()
    readback=cli('artifact','show',result['artifact'])
    assert readback['output_blob']==result['output_blob'] and readback['output_role']==role
    assert any(q['question_id']==QUESTION and q['relationship']=='produced' for q in readback['questions'])
    (REG/(role+'.readback.json')).write_text(json.dumps(readback,indent=2))
    print(role,result['artifact'],result['output_blob'],'verified')
