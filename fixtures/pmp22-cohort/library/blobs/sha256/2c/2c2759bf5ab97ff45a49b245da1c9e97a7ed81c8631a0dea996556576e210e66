"""Register selected executed follow-up outputs and verify exact catalog targets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]
a=argparse.ArgumentParser()
a.add_argument('--first-only', action='store_true')
args=a.parse_args()
regdir=q/'outputs/registrations-followups-r001'
regdir.mkdir(exist_ok=True)

def cli(argv):
    p=subprocess.run(['./bin/bio', *argv],capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError(p.stderr)
    return json.loads(p.stdout)

def add(p):
    v=cli(['object','add',str(p)])
    assert v['blob']==hashlib.sha256(p.read_bytes()).hexdigest()
    return v['blob']

receipt_path=q/'outputs/execution-independent-r006.json'
receipt=json.loads(receipt_path.read_text())
assert receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged']
code=q/'scripts/analyze_independent_pum.py'
assert hashlib.sha256(code.read_bytes()).hexdigest()==receipt['code_sha256']
inputs=[]
for item in json.loads((q/'outputs/independent-r001/input-manifest.json').read_text()):
    p=q/item['path']
    assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
    inputs.append(add(p))
inputs += [m['acquisition']['blob'] for m in json.loads((q/'inputs/independent/tcam-native-inputs.json').read_text())]
inputs += [add(receipt_path)]
selected=['PMP22-endpoints.tsv','summary.json','complete-backgrounds.json','perturbation-controls.tsv','prediction-result.json','bruchase-native-coefficients.tsv']
registered=[]
for name in selected:
    target=next(x for x in receipt['outputs'] if Path(x['path']).name==name)
    p=Path(target['path'])
    assert target['written'] and hashlib.sha256(p.read_bytes()).hexdigest()==target['sha256']
    dest=regdir/(name+'.json')
    if dest.exists():
        rec=json.loads(dest.read_text())
    else:
        command=['register',str(p),'--question',q.name,'--title','PMP22 independent PUM/CNOT audit: '+name,'--summary','Executed native full-background audit: conditional TCam PUM1 response; failed HEK293 PUM persistence prediction; HCT116 PUM nonsignificant/CNOT positive; endpoint and source-export limitations retained.','--code',str(code),'--output-role','independent-'+name,'--parameters',json.dumps({'execution_receipt_sha256':inputs[-1], 'run':'independent-r006'})]
        for value in inputs:
            command+=['--input',value]
        rec=cli(command)
        dest.write_text(json.dumps(rec,indent=2,allow_nan=False))
    assert rec['output_blob']==target['sha256']
    shown=cli(['artifact','show',rec['artifact']])
    assert shown['output_blob']==target['sha256']
    (regdir/(name+'.readback.json')).write_text(json.dumps(shown,indent=2,allow_nan=False))
    registered.append({'name':name,'artifact':rec['artifact'],'output_blob':rec['output_blob']})
    print(json.dumps(registered[-1]),flush=True)
    if args.first_only:
        break
if not args.first_only:
    (q/'outputs/followup-artifacts.json').write_text(json.dumps(registered,indent=2,allow_nan=False))
