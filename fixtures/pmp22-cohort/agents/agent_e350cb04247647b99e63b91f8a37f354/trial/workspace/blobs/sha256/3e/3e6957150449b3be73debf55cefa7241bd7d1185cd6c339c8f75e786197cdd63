"""Register actual producing outputs; persist each receipt and read back exact bytes."""
import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q/'outputs'

def bio(*args):
    result = subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(result.stdout)

receipt = json.loads((out/'execution-r002.json').read_text())
assert receipt['complete'] and receipt['exit_code']==0
receipt_hash = hashlib.sha256((out/'execution-r002.json').read_bytes()).hexdigest()
first = json.loads((out/'registration-summary.json').read_text())
assert first['artifact'].startswith('artifact_') and not first['conflicting_outputs'] and first['warning'] is None
info = bio('artifact','show',first['artifact'])
assert info['output_blob']==first['output_blob']==hashlib.sha256((out/'summary.json').read_bytes()).hexdigest()
assert info['manifest']['derivation']['parameters']['execution_receipt_sha256']==receipt_hash
(out/'registration-summary-readback.json').write_text(json.dumps(info,indent=2))
inputs = [r['artifact'] for k,r in json.loads((q/'sources/immutable-inputs.json').read_text()).items() if k in ['native','mapping','samples']]
inputs.append('48ede62f1d447648a1a5df4b6337bfe29115eff65105e022cdb8290c0b1ec740')
index = {'summary.json':first['artifact']}
regdir = out/'registrations'
regdir.mkdir(exist_ok=True)
for produced in receipt['outputs']:
    name = Path(produced['path']).name
    if name=='summary.json':
        continue
    path = out/name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==produced['sha256']
    saved = regdir/(name+'.json')
    if saved.exists():
        result = json.loads(saved.read_text())
    else:
        args = ['register',str(path),'--question',q.name,'--title','PMP22 promoter responses: '+name,
                '--summary','Individual-library rat start-associated RNA; descriptive only, no donor inference or nascent initiation.',
                '--code',str(q/'scripts/analyze_responses.py'),'--reference',receipt_hash,
                '--parameters',json.dumps({'execution_receipt_sha256':receipt_hash,'units':'RPM','uncertainty':'descriptive sensitivity','spec_sha256':inputs[-1]}),
                '--output-role',name]
        for item in inputs:
            args.extend(['--input',item])
        result = bio(*args)
        saved.write_text(json.dumps(result,indent=2))
    assert not result['conflicting_outputs'] and result['warning'] is None
    readback = bio('artifact','show',result['artifact'])
    assert readback['output_blob']==produced['sha256']
    assert Path(readback['path']).read_bytes()==path.read_bytes()
    (regdir/(name+'.readback.json')).write_text(json.dumps(readback,indent=2))
    index[name]=result['artifact']
    print('REGISTERED_VERIFIED',name,result['artifact'])
(out/'registered-quantitative-products.json').write_text(json.dumps(index,indent=2))
assert len(index)==len(receipt['outputs'])
print('VERIFIED_REGISTERED_TOTAL',len(index))
