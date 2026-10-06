"""Register the corrected evidence package without altering prior catalog artifacts."""
from pathlib import Path
import json,subprocess,hashlib
Q=Path(__file__).resolve().parents[1];U=Q/'outputs/upstream';I=Q/'inputs/upstream';B=str(Q.parents[2]/'bin/bio')
def cli(a):return json.loads(subprocess.run([B,*a],capture_output=True,text=True,check=True).stdout)
p=U/'analysis-package.json';x=json.loads(p.read_text());(U/'analysis-package.r001.json').write_bytes(p.read_bytes());old=json.loads((U/'final-registration.json').read_text())[-1]['receipt']['artifact'];updated=[]
for path in [U/'REPORT.md',U/'novelty-audit.json',U/'transport-final.json',I/'web-searches.json',I/'web-final-correction.json',Q/'outputs/investigations.r029.json',Q/'scripts/upstream_browser_receipt.py',Q/'scripts/upstream_link_final.py']:
 r=cli(['object','add',str(path),'--classification','interpretation']);entry=dict(path=str(path.relative_to(Q)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),receipt=r);updated.append(entry);x['files']=[a for a in x['files'] if a['path']!=entry['path']]+[entry]
x['revision']=2;x['supersedes']=old;x['correction']='Unsupported hand-authored browser activity withdrawn. Actual direct HTTP and bio acquisition receipts remain authoritative; scientific outputs and statuses unchanged.';x['current_queue']='outputs/investigations.r029.json'
for path in [p,U/'analysis-package.r002.json']:path.write_text(json.dumps(x,indent=2))
a=['register',str(U/'analysis-package.r002.json'),'--question',Q.name,'--title','PMP22 upstream evidence package r002: corrected transport/source provenance','--output-role','upstream-evidence-package','--input',old,'--code',str(Q/'scripts/upstream_package_correction.py'),'--code',str(Q/'scripts/upstream_browser_receipt.py'),'--parameters',json.dumps(dict(revision=2,scientific_results_unchanged=True,browser_claim_withdrawn=True))]
for r in updated:a+=['--input',r['receipt']['blob']]
r=cli(a);(U/'final-registration-r002.json').write_text(json.dumps(r,indent=2));back=cli(['artifact','show',r['artifact']]);assert back['id']==r['artifact'];(U/'final-registration-r002-readback.json').write_text(json.dumps(back,indent=2));print(json.dumps(r,indent=2))
