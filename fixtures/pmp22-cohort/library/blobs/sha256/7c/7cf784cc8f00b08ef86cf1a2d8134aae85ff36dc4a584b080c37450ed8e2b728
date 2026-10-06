"""Register the inspected ZIP with its own packaging receipt and member inputs."""
import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q/'outputs'

def bio(*args):
    return json.loads(subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True).stdout)

receipt_path = out/'packaging-execution-r001.json'
receipt = json.loads(receipt_path.read_text())
assert receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged']
receipt_blob = bio('object','add',str(receipt_path),'--classification','reference')['blob']
member_manifest = json.loads((out/'bundle-members.json').read_text())
inputs = []
member_receipts = []
for item in member_manifest['files']:
    path = q/item['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
    stored = bio('object','add',str(path),'--classification','code' if path.suffix=='.py' else 'source')
    assert stored['blob']==item['sha256']
    inputs.append(stored['blob'])
    member_receipts.append({'member':item['path'],**stored})
(out/'bundle-member-preservation.json').write_text(json.dumps(member_receipts,indent=2))
manifest_blob = bio('object','add',str(out/'bundle-members.json'),'--classification','reference')['blob']
products = json.loads((out/'registered-quantitative-products.json').read_text())
args = ['register',str(out/'pmp22-promoter-responses.zip'),'--question',q.name,
        '--title','PMP22 P1/P2 quantitative response analysis: sources, code, tables, figures and evidence audit',
        '--summary','Executed GSE139321 descriptive analysis: robust relative P1 loss with SOX10 knockout and fragile cAMP preference; sample-design and selected-universe limits retained.',
        '--code',str(q/'scripts/package_results.py'),'--reference',receipt_blob,'--reference',manifest_blob,
        '--parameters',json.dumps({'execution_receipt_sha256':receipt_blob,'operation':'package verified analysis outputs and primary-source evidence','scientific_producer_receipt':'d297442fb7273f1b97f6db265646701b8192db7af12034889c4eb1088cd833aa','no_new_scientific_rerun':True}),
        '--output-role','pmp22-response-analysis-bundle']
for value in sorted(set(inputs)):
    args.extend(['--input',value])
for value in products.values():
    args.extend(['--input',value])
result = bio(*args)
(out/'registration-bundle.json').write_text(json.dumps(result,indent=2))
assert not result['conflicting_outputs'] and result['warning'] is None
info = bio('artifact','show',result['artifact'])
assert info['output_blob']==hashlib.sha256((out/'pmp22-promoter-responses.zip').read_bytes()).hexdigest()
assert Path(info['path']).read_bytes()==(out/'pmp22-promoter-responses.zip').read_bytes()
(out/'registration-bundle-readback.json').write_text(json.dumps(info,indent=2))
print('REGISTERED_VERIFIED_BUNDLE',result['artifact'])
