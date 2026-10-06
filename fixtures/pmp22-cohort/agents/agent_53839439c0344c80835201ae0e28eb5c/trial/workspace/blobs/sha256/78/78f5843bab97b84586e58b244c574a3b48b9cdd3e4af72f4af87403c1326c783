"""Register one verified peer-review result and read back its exact target."""
import hashlib
import json
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]
o=q/'outputs/rbp-review'

def cli(args):
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

p=o/'pum2-screen-review.json'
data=json.loads(p.read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
r=json.loads((o/'execution-r003.json').read_text())
assert r['complete'] and r['exit_code']==0 and r['code_unchanged']
assert hashlib.sha256((q/'scripts/review_pum_screen.py').read_bytes()).hexdigest()==r['code_sha256']
assert hashlib.sha256(p.read_bytes()).hexdigest()==r['outputs'][0]['sha256']
refs=[cli(['object','add',str(o/name)])['blob'] for name in ['execution-r001.json','execution-r002.json','execution-r003.json']]
args=['register',str(p),'--question',q.name,'--title','PUM2 screen critique: endpoint identifiability and source checks',
      '--summary','Independent reader of peer-derived PUM tables; no new biological replication; conditional ActD algebra; GSE118660 assay-label erratum',
      '--code',str(q/'scripts/review_pum_screen.py'),'--output-role','pum2-screen-review',
      '--parameters',json.dumps({'raw_processing':False,'DE_refit':False,'empirical_decay_fit':False,'source_thresholds_unchanged':True})]
for entry in data['inputs']:
    args+=['--input',entry['blob']]
for h in refs:
    args+=['--reference',h]
result=cli(args)
(o/'registration.json').write_text(json.dumps(result,indent=2))
assert not result['conflicting_outputs']
assert result['output_blob']==hashlib.sha256(p.read_bytes()).hexdigest()
readback=cli(['artifact','show',result['artifact']])
(o/'artifact-readback.json').write_text(json.dumps(readback,indent=2))
assert readback['id']==result['artifact'] and readback['output_blob']==result['output_blob']
print(json.dumps(result))
