"""Register only successful producer-declared outputs; read back each artifact."""
from pathlib import Path
import argparse,json,hashlib,subprocess,sys,platform,importlib.metadata
Q=Path(__file__).resolve().parents[1];W=Q.parents[1];ROOT=W.parent;O=Q/'outputs';R=O/'registrations';R.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bio(*args):
 r=subprocess.run([str(ROOT/'bin/bio'),*map(str,args)],capture_output=True,text=True,check=True);return json.loads(r.stdout)
def save(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
parser=argparse.ArgumentParser();parser.add_argument('--first-only',action='store_true');args=parser.parse_args()
env=O/'analysis-environment.json'
if not env.exists():save(env,dict(python=sys.version,platform=platform.platform(),libraries={m:importlib.metadata.version(m) for m in ['numpy','pandas','scipy','openpyxl','matplotlib','requests']},interpretation='Question-local scripts; no downloaded code executed'))
# Inputs actually consumed by producers plus native derivation dependencies.
common=[]
for p in sorted((O/'matrices').glob('*.tsv.gz'))+[O/'GSE177037-design-summary.json',O/'inherited-antioxidant-summary.json',O/'preparation-summary.json']:
 h=sha(p)
 if not (W/'blobs/sha256'/h[:2]/h).exists():bio('object','add',p)
 common.append(h)
common+=list({r['blob'] for r in json.loads((O/'preparation-summary.json').read_text())['inputs']})
for p in (Q/'inputs/managed').glob('*.fetch.json'):
 r=json.loads(p.read_text())
 if 'blob' in r:common.append(r['blob'])
for p in [Q/'inputs/public/GSE137947-gsm.soft',Q/'inputs/public/GSE138577-family.soft']:
 common.append(bio('object','add',p)['blob'])
# Main state summary first, then inspect receipt before registration continuation.
receipts=['state-execution-r002.json','composition-execution-r001.json','robustness-execution-r001.json','burden-execution-r001.json','prepare-execution-r002.json']
registered=[]
for name in receipts:
 p=O/name;e=json.loads(p.read_text());assert e['complete'] and e['exit_code']==0 and sha(Path(e['producer']))==e['code_sha256'];rh=bio('object','add',p)['blob']
 code=[Path(e['producer'])]
 if name.startswith(('state','prepare')):code.extend([Q/'scripts/prepare_matrices.py',Q/'scripts/xls_values.py'])
 if name.startswith('composition'):code.append(Q/'scripts/xls_values.py')
 for v in e['outputs']:
  path=Path(v['path']);assert v['written'] and sha(path)==v['sha256'];dest=R/(path.name+'.registration.json')
  if dest.exists():registered.append(json.loads(dest.read_text())['artifact']);continue
  # Explicit parent result inputs for the retrospective computation.
  dependencies=list(common)
  if name.startswith('robustness'):
   for dep in ['reference-effects.tsv','projection-residuals.tsv.gz','composition-compatibility.tsv','composition-summary.json','bulk-panel-effects.tsv','cell-reference-QC.tsv','repair-samples.tsv']:
    dependencies.append(bio('object','add',O/dep)['blob'])
  cmd=['register',path,'--question',Q.name,'--title','PMP22 composition/state follow-up: '+path.name,'--summary','Actual processed mouse developmental/sorted/P1 atlas and inherited Nae1/mTOR/rat repair measurements; reference-restricted sensitivity, not causal proof. See question evidence index.','--output-role',path.name.replace('.','-'),'--parameters',json.dumps(dict(execution_receipt=rh,comparison_plan='outputs/decision-r002.txt',retrospective_bulk=True,reference_independence='P5 paired subjects; P1 independent biological pools, not cells')),'--environment',env]
  for c in dict.fromkeys(code):cmd+=['--code',c]
  for h in sorted(set(dependencies+[rh])):cmd+=['--input',h]
  reg=bio(*cmd);save(dest,reg);assert not reg.get('conflicting_outputs') and not reg.get('warning'),reg
  rb=bio('artifact','show',reg['artifact']);save(R/(path.name+'.readback.json'),rb);assert rb['output_blob']==sha(path)==reg['output_blob'];assert any(z['question_id']==Q.name for z in rb['questions']);registered.append(reg['artifact']);print(path.name,reg['artifact'],'readback verified',flush=True)
  if args.first_only:raise SystemExit(0)
print('Total producer-declared registered outputs',len(registered))
