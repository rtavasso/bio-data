"""Register executed products only, verifying producer/output hashes and exact readback."""
import hashlib
import json
from pathlib import Path
import subprocess

q = Path(__file__).resolve().parents[1]
o = q / 'outputs'
rdir = o / 'registrations-final'
rdir.mkdir(exist_ok=True)

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def bio(args):
    p = subprocess.run(['./bin/bio', *args], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)

def obj(p):
    return bio(['object','add',str(p)])['blob']

base = json.loads((q/'inputs/frozen-manifest-r001.json').read_text())
base_inputs = {v['blob'] for v in base.values()}
base_inputs.update(v['receipt_blob'] for v in base.values() if 'receipt_blob' in v)
base_inputs.add(obj(q/'inputs/frozen-manifest-r001.json'))
ext = json.loads((q/'inputs/extension-manifest.json').read_text())
extra = {v['sha256'] for v in ext.values()}
extra.add(obj(q/'inputs/extension-manifest.json'))
registrations = {}
for label, inputset in [('ends-r004',base_inputs), ('extension-r002',base_inputs | extra)]:
    rp = o/f'execution-{label}.json'
    receipt = json.loads(rp.read_text())
    assert receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged']
    code = Path(receipt['producer'])
    assert sha(code)==receipt['code_sha256']
    receipt_hash = obj(rp)
    inputs = set(inputset) | {receipt_hash}
    if label.startswith('extension'):
        base_receipt = json.loads((o/'execution-ends-r004.json').read_text())
        for result in base_receipt['outputs']:
            inputs.add(obj(Path(result['path'])))
        inputs.add(obj(o/'execution-ends-r004.json'))
    for result in receipt['outputs']:
        path = Path(result['path'])
        assert result['written'] and sha(path)==result['sha256']
        args = ['register',str(path),'--question',q.name,'--title','PMP22 RNA ends: '+path.name,'--summary','Executed observed-end/site retention and perturbation comparison. Annotation, selected-out and measured calls separate; no Schwann transfer or decay claim.','--code',str(code),'--parameters',json.dumps({'producer_receipt_sha256':receipt_hash,'analysis_version':label,'argv':receipt['argv']}),'--output-role',path.name]
        for h in sorted(inputs):
            args.extend(['--input',h])
        value = bio(args)
        (rdir/(path.name+'.registration.json')).write_text(json.dumps(value,indent=2))
        aid = value['artifact']
        readback = bio(['artifact','show',aid])
        assert readback['output_blob']==result['sha256']
        (rdir/(path.name+'.readback.json')).write_text(json.dumps(readback,indent=2))
        registrations[path.name] = {'artifact':aid,'output_blob':result['sha256'],'producer_receipt_sha256':receipt_hash}
        print(path.name, aid)
(o/'registrations-final.json').write_text(json.dumps(registrations,indent=2))
