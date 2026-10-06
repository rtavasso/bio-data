"""Preserve inherited state and begin a new question-local continuation."""
from pathlib import Path
import json, datetime, subprocess, importlib
Q=Path(__file__).resolve().parents[1]; ROOT=Q.parents[2]; O=Q/'outputs/upstream'; I=Q/'inputs/upstream'
I.mkdir(exist_ok=True); O.mkdir(exist_ok=True)
def save(p,x):
    with p.open('x') as f: json.dump(x,f,indent=2,allow_nan=False)
for n in ['investigations','mechanisms','discoveries']:
    p=Q/'outputs'/f'{n}.json'; x=json.loads(p.read_text()); save(O/f'{n}.inherited.json',x)
x=json.loads((Q/'outputs/investigations.json').read_text()); x['revision']=24;x['status']='in_progress';x['stopping_reason']='New upstream/non-transcriptional continuation; bounded discovery and experiment comparison precede selection.'
x['items'].append(dict(id='upstream-indirect-perturbation',priority='high',question='Does an upstream metabolic or RNA-processing perturbation distinguish PMP22 regulation from a generic Schwann-cell state response?',alternatives=['target-selective RNA or protein regulation','general differentiation/metabolic program','context or measurement artifact'],readout='Complete processed perturbation matrices with sample-level metadata; orthogonal endpoints when available',assets=[],prerequisites=['Compare exact designs, independent units and prior exposure','Source-status and feature eligibility before analysis'],status='open',artifacts=[],finding='',limitation='Study selection pending bounded mechanism/assay discovery',next_action='Search without PMP22 terms; inspect promising metadata and save selection checkpoint',blocker_evidence=[],decision='outputs/upstream/decision-r001.md'))
(Q/'outputs/investigations.json').write_text(json.dumps(x,indent=2,allow_nan=False)+'\n');save(Q/'outputs/investigations.r024.json',x)
env={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'libraries':{}}
for m in ['numpy','pandas','scipy','matplotlib','requests','openpyxl','statsmodels']:
    try: mod=importlib.import_module(m);env['libraries'][m]=getattr(mod,'__version__','available')
    except ImportError:env['libraries'][m]='not available'
save(O/'environment.json',env)
save(I/'transport.json',dict(allowance='unlimited requests/file/bytes/time; current continuation only',direct_requests=0,downloaded_bytes=0,browser_queries=0,browser_bytes_estimated=0,events=[]))
receipts=[]
for p in [O/'decision-r001.md',Q/'outputs/investigations.r024.json']:
    r=subprocess.run([str(ROOT/'bin/bio'),'object','add',str(p),'--classification','interpretation'],capture_output=True,text=True,check=True);receipts.append(dict(path=str(p.relative_to(Q)),receipt=json.loads(r.stdout)))
save(O/'checkpoint-r001-receipts.json',receipts)
with (Q/'LABBOOK.md').open('a') as f:f.write('\n\n## Upstream continuation intake — '+env['started_utc']+'\nRead inherited notebook, rejected hypotheses and source limits; intake link/status checks pass. New work under outputs/upstream and inputs/upstream. No replacement question or new credit for inherited work. Decision-r001 compares metabolic/nuclear-receptor, non-transcriptional, large processed proteomics and familiar-source options before new discovery. Queue r024 saved/preserved; receipts in outputs/upstream/checkpoint-r001-receipts.json. Current limits unlimited; prior size blockers will be reassessed when relevant.\n')
print(json.dumps({'environment':env,'checkpoints':receipts},indent=2))
