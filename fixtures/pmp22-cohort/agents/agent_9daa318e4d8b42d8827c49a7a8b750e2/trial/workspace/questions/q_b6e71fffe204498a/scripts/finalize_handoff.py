"""Preserve final interpretation, register verified bundle, and validate all handoff links."""
from pathlib import Path
import json,hashlib,subprocess,tarfile
Q=Path(__file__).resolve().parents[1];W=Q.parents[1];ROOT=W.parent;O=Q/'outputs'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bio(*args):
 p=subprocess.run([str(ROOT/'bin/bio'),*map(str,args)],capture_output=True,text=True,check=True);return json.loads(p.stdout)
def save(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
preserved={}
for name in ['REPORT.md','evidence-index.json','RETRIEVAL_POINTER.txt','investigations.r002.json','investigations.json','mechanisms.r002.json','mechanisms.json','evidence-coverage.tsv','causal-design-evidence.txt','retrieval-ledger.json','schema-check-r001.json','status-check-r001.txt','prediction-check-r001.txt','package-manifest.json','package-execution-r001.json']:
 p=O/name;preserved[name]=bio('object','add',p,'--classification','interpretation')
 for_sha=preserved[name]['blob'];assert for_sha==sha(p)
receipt=json.loads((O/'package-execution-r001.json').read_text());assert receipt['complete'] and receipt['exit_code']==0 and sha(Path(receipt['producer']))==receipt['code_sha256']
for x in receipt['outputs']:assert x['written'] and sha(Path(x['path']))==x['sha256']
cmd=['register',O/'package-analysis.tar.gz','--question',Q.name,'--title','PMP22 composition and developmental-state follow-up: complete analysis bundle','--summary','Processed reference/bulk matrices, scripts, actual execution receipts, corrected inherited evidence index and source-backed limitations. Normal-state sufficiency weakened; actual cell source and NRF2 mediation unidentified.','--code',Q/'scripts/package_analysis.py','--output-role','composition-state-analysis-bundle','--parameters',json.dumps(dict(execution_receipt=sha(O/'package-execution-r001.json'),manifest=sha(O/'package-manifest.json'),does_not_replace_producer_receipts=True))]
for h in [preserved['package-manifest.json']['blob'],preserved['package-execution-r001.json']['blob']]:cmd+=['--input',h]
for p in sorted((O/'registrations').glob('*.registration.json')):cmd+=['--input',json.loads(p.read_text())['artifact']]
r=bio(*cmd);save(O/'package-registration.json',r);assert not r.get('conflicting_outputs') and not r.get('warning')
b=bio('artifact','show',r['artifact']);save(O/'package-registration-readback.json',b);assert b['output_blob']==sha(O/'package-analysis.tar.gz')==r['output_blob'];assert any(z['question_id']==Q.name for z in b['questions'])
checks=[];registered=[]
for p in sorted((O/'registrations').glob('*.registration.json')):
 z=json.loads(p.read_text());rb=bio('artifact','show',z['artifact']);assert rb['output_blob']==z['output_blob'];assert any(a['question_id']==Q.name for a in rb['questions']);registered.append(z['artifact'])
checks.append(dict(check='Registered computation output hashes and exact question links',passed=True,count=len(registered)))
for name in ['prepare-execution-r002.json','state-execution-r002.json','composition-execution-r001.json','robustness-execution-r001.json','burden-execution-r001.json','package-execution-r001.json']:
 e=json.loads((O/name).read_text());assert e['complete'] and e['exit_code']==0 and sha(Path(e['producer']))==e['code_sha256']
 for x in e['outputs']:assert x['written'] and sha(Path(x['path']))==x['sha256']
checks.append(dict(check='Six actual producing invocations, unchanged code and output hashes',passed=True))
manifest=json.loads((O/'package-manifest.json').read_text())
with tarfile.open(O/'package-analysis.tar.gz','r:gz') as t:
 assert len(t.getmembers())==manifest['member_count']+1
 for x in manifest['members']:
  assert sha(Q/x['path'])==x['sha256'],x['path'];assert hashlib.sha256(t.extractfile(x['path']).read()).hexdigest()==x['sha256']
checks.append(dict(check='Archive members equal exact current inputs; no extraction/code execution',passed=True,count=manifest['member_count']+1))
source_blobs=set()
for x in json.loads((O/'preparation-summary.json').read_text())['inputs']:source_blobs.add(x['blob'])
for p in (Q/'inputs/managed').glob('*.fetch.json'):
 x=json.loads(p.read_text())
 if 'blob' in x:source_blobs.add(x['blob'])
for h in source_blobs:assert sha(W/'blobs/sha256'/h[:2]/h)==h
checks.append(dict(check='Exact underlying source/dependency blob hashes',passed=True,count=len(source_blobs)))
for label,command in [('full_schema_reference_check',[str(ROOT/'bin/python'),'-m','daw.research_records',str(Q)]),('mechanism_status_coverage_check',[str(ROOT/'bin/python'),str(ROOT/'.agents/skills/bio-mechanism-exploration/scripts/check_statuses.py'),str(Q)])]:
 p=subprocess.run(command,capture_output=True,text=True);save(O/('final-handoff-'+label+'.json'),dict(argv=command,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0;assert json.loads(p.stdout)['valid'];checks.append(dict(check=label,passed=True))
queue=json.loads((O/'investigations.json').read_text());assert all(x['status'] in ['analyzed','blocked'] for x in queue['items'] if x['priority']=='high');assert not any(x['status']=='deferred' and x['priority']=='high' for x in queue['items'])
checks.append(dict(check='High-priority scope closure: executed or source-evidenced blocked, no deferred high branch',passed=True))
result=dict(valid=True,question=Q.name,checks=checks,registered_computations=registered,bundle_artifact=r['artifact'],bundle_sha256=sha(O/'package-analysis.tar.gz'),interpretation_objects=preserved,prediction_link_check='Not applicable: no discoveries.json or structured prediction authored; optional-helper missing-file result retained. Actual falsifiable sensitivity plan and its preserved hash are present.',scientific_limits='Mechanical pass does not identify cell fractions, cell-intrinsic effect, NRF2 mediation, promoter activity or independent replication.')
save(O/'final-handoff-verification.json',result);bio('object','add',O/'final-handoff-verification.json','--classification','interpretation')
print(json.dumps(dict(valid=True,checks=len(checks),registered_computations=len(registered),bundle_artifact=r['artifact'],archive_members=manifest['member_count']+1),indent=2))
