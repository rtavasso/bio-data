"""Register first executed RNA result with complete file dependencies; reusable later."""
from pathlib import Path
import json,subprocess
Q=Path(__file__).resolve().parents[1];ROOT=Q.parents[2];I=Q/'inputs/upstream';O=Q/'outputs/upstream';BIO=str(ROOT/'bin/bio')
def cli(args):
 r=subprocess.run([BIO,*args],capture_output=True,text=True,check=True);return json.loads(r.stdout)
objects=[]
for p in [I/'rna-fetch-receipts.json',O/'prediction-r001.json',O/'prediction-seal-receipt.json']:
 rr=cli(['object','add',str(p)]);objects.append(dict(path=str(p.relative_to(Q)),receipt=rr))
(O/'rna-dependency-objects.json').write_text(json.dumps(objects,indent=2))
inputs=[a['receipt']['asset_revision'] for a in json.loads((I/'rna-fetch-receipts.json').read_text())]+[a['receipt']['blob'] for a in objects]
args=['register',str(O/'nae1-RNA-summary.json'),'--question',Q.name,'--title','PMP22 Nae1 independent RNA relative-preservation test','--code',str(Q/'scripts/upstream_analyze_nae1.py'),'--output-role','nae1-rna-summary','--parameters',json.dumps(dict(sealed_plan='0344d7d2d0e07d9457ff74d947fc37c79d96f1e1c13922fdfed6a360ae3cba90',pseudocount=.5,normalization='median-ratio; within-sample primary statistic'))]
for v in inputs:args+=['--input',v]
r=cli(args);(O/'rna-first-registration.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
