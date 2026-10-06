"""Register source-complete test artifacts and a portable analysis-output manifest."""
from pathlib import Path
import json,subprocess,hashlib,platform,importlib.metadata
Q=Path(__file__).resolve().parents[1];O=Q/'outputs';U=O/'upstream';I=Q/'inputs/upstream';B=str(Q.parents[2]/'bin/bio')
def cli(args):
 r=subprocess.run([B,*args],capture_output=True,text=True,check=True);return json.loads(r.stdout)
def obj(p,classification='source'):
 r=cli(['object','add',str(p),'--classification',classification]);return dict(path=str(p.relative_to(Q)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),receipt=r)
# Environment uses inspected installed packages, not a guessed requirements file.
env=dict(python=platform.python_version(),platform=platform.platform(),packages={p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','openpyxl','matplotlib','requests']})
(U/'environment.json').write_text(json.dumps(env,indent=2))
source_paths=[I/'elife-29241-fig3-data1.xlsx',I/'Figlia2017-supplements.zip',I/'PRJEB20661-samples.tsv',I/'PRJEB20661-library.tsv',I/'rna-fetch-receipts.json',U/'prediction-r001.json',U/'antioxidant-prediction-r001.json',U/'antioxidant-seal-receipt.json',U/'nae1-all-expected-counts.tsv',U/'nae1-all-log2normalized.tsv',U/'Figlia-extraction.json']
source_paths += sorted(I.glob('PMC*.xml'))+sorted(I.glob('novelty-*.json'))+sorted((I/'receipts').glob('*.json'))
inputs=[obj(p) for p in dict.fromkeys(source_paths)];(U/'final-input-objects.json').write_text(json.dumps(inputs,indent=2))
base=[r['receipt']['blob'] for r in inputs]+[r['receipt']['asset_revision'] for r in json.loads((I/'rna-fetch-receipts.json').read_text())]
first=json.loads((U/'rna-first-registration.json').read_text())['artifact'];base+=[first]
registrations=[]
def reg(path,title,role,code,ins,params):
 args=['register',str(path),'--question',Q.name,'--title',title,'--output-role',role,'--parameters',json.dumps(params),'--environment',str(U/'environment.json')]
 for p in code:args+=['--code',str(Q/'scripts'/p)]
 for x in ins:args+=['--input',x]
 r=cli(args);registrations.append(dict(path=str(path.relative_to(Q)),receipt=r));return r
locked=reg(U/'antioxidant-summary.json','PMP22 Nae1 vs mTOR five-gene comparator: locked test untestable','locked-antioxidant-test',['upstream_analyze_nae1.py','upstream_analyze_antioxidant.py'],base,dict(status='untestable',prediction_sha256=json.loads((U/'antioxidant-seal-receipt.json').read_text())['sha256']))
post=reg(U/'antioxidant-posthoc-summary.json','PMP22 Nae1 antioxidant separation: exploratory eligible four-gene comparison','exploratory-antioxidant-comparison',['upstream_analyze_nae1.py','upstream_analyze_antioxidant.py','upstream_antioxidant_followup.py'],base+[locked['artifact']],dict(status='retrospective_exploratory_not_validation',genes=['Nqo1','Hmox1','Gclc','Gclm'],units='mouse libraries; shared mTOR controls retained'))
# All substantive useful outputs are addressed by their immutable blob hashes.
files=[]
for pattern in ['nae1-*.json','nae1-*.tsv','nae1-*.png','nae1-*.pdf','antioxidant-*.json','antioxidant-*.tsv','antioxidant-*.png','antioxidant-*.pdf','proteome-mzid-inspection.json','novelty-audit.json','reported-numbers.json','transport-final.json','validation.json','REPORT.md','environment.json']:
 for p in sorted(U.glob(pattern)):
  if p.name not in [Path(a['path']).name for a in files]:files.append(obj(p,'interpretation'))
for name in ['mechanisms.r021.json','investigations.r028.json','discoveries.r008.json','evidence-coverage.r020.tsv']:
 files.append(obj(O/name,'interpretation'))
for p in sorted((Q/'scripts').glob('upstream_*.py')):files.append(obj(p,'interpretation'))
package=dict(question=Q.name,scope='Upstream continuation only; inherited scientific work referenced but not claimed new',artifacts=dict(rna=first,locked=locked['artifact'],exploratory=post['artifact']),files=files,input_objects=inputs,report='outputs/upstream/REPORT.md',validity='133 initial plus full normalization check; consult exact validation.json count',limits='Exploratory comparator is not NRF2 causality or successful locked validation; see REPORT and queue')
(U/'analysis-package.json').write_text(json.dumps(package,indent=2))
pkg=reg(U/'analysis-package.json','PMP22 upstream continuation evidence package and source-audited report','upstream-evidence-package',['upstream_register_final.py','upstream_verify.py'],[first,locked['artifact'],post['artifact']]+[a['receipt']['blob'] for a in files],dict(scope='scientific_data_manifest_and_authored_report',no_causal_novelty_claim=True))
(U/'final-registration.json').write_text(json.dumps(registrations,indent=2));print(json.dumps(registrations,indent=2))
# Required external-state read-back: exact artifact targets, not success replies alone.
reads=[]
for rr in registrations:
 ident=rr['receipt']['artifact'];detail=cli(['artifact','show',ident]);reads.append(dict(artifact=ident,detail=detail))
(U/'final-registration-readback.json').write_text(json.dumps(reads,indent=2));print('Exact artifact read-backs complete:',len(reads))
