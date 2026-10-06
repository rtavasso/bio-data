"""Register and read back only outputs validated against their actual producer receipt."""
import hashlib
import json
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]
o=q/'outputs/registrations-screen-r002'
o.mkdir(exist_ok=True)

def cli(args):
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True)
    if p.returncode:
        print(p.stderr)
        p.check_returncode()
    return json.loads(p.stdout)

rp=q/'outputs/execution-screen-r002.json'
receipt=json.loads(rp.read_text())
assert receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged']
producer=q/'scripts/screen.py'
assert hashlib.sha256(producer.read_bytes()).hexdigest()==receipt['code_sha256']
manifestpath=q/'inputs/screen-manifest-r001.json'
manifest=json.loads(manifestpath.read_text())
for p in [rp,manifestpath]:
    cli(['object','add',str(p)])
inputs=[v['sha256'] for v in manifest['files']]+[hashlib.sha256(manifestpath.read_bytes()).hexdigest(),hashlib.sha256(rp.read_bytes()).hexdigest()]
for output in receipt['outputs']:
    p=Path(output['path'])
    assert output['written'] and hashlib.sha256(p.read_bytes()).hexdigest()==output['sha256']
    if p.suffix=='.json':
        json.loads(p.read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
    dest=o/(p.name+'.registration.json')
    if dest.exists():
        registered=json.loads(dest.read_text())
    else:
        args=['register',str(p),'--question',q.name,'--title','PMP22 ENCORE screen: '+p.name,'--summary','Executed complete 223-context binding and 203 matched perturbation screen; no joint hits; coverage, full backgrounds and untestable entries retained.','--code',str(producer),'--output-role',p.name,'--parameters',json.dumps({'execution_receipt_sha256':hashlib.sha256(rp.read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256(manifestpath.read_bytes()).hexdigest(),'screen':'r002'})]
        for value in inputs:
            args+=['--input',value]
        registered=cli(args)
        dest.write_text(json.dumps(registered,indent=2))
    assert registered['output_blob']==output['sha256']
    shown=cli(['artifact','show',registered['artifact']])
    (o/(p.name+'.readback.json')).write_text(json.dumps(shown,indent=2))
    print(p.name,registered['artifact'])
