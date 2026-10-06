"""Register actual producer outputs with receipts and readback validation."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
OUT = Q/'outputs'
REG = OUT/'registrations'
REG.mkdir(exist_ok=True)
CACHE = {}

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def bio(args):
    p = subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

def obj(path):
    path = path.resolve()
    if path not in CACHE:
        r = bio(['object','add',str(path)])
        assert r['blob']==sha(path)
        CACHE[path] = r['blob']
    return CACHE[path]

parser=argparse.ArgumentParser()
parser.add_argument('--first',action='store_true')
parser.add_argument('--bundle',action='store_true')
args=parser.parse_args()
manifest=json.loads((Q/'inputs/acquisition/manifest.json').read_text())
native=[W/x['path'] for x in manifest]
base=[*native,Q/'inputs/acquisition/manifest.json',OUT/'prediction-draft.json',OUT/'predictions/mechanical-transfer-r001.json',*[Q/f'inputs/primary/{s}-family.soft' for s in ['GSE94990','GSE98547','GSE292211']],Q.parent/'q_e835197734394f30/inputs/primary/GSE79115-samples.soft']
main_receipt=json.loads((OUT/'analysis-execution-r003.json').read_text())
main_outputs=[OUT/Path(x['path']).name for x in main_receipt['outputs']]
validation_inputs=[*base,*main_outputs,*sorted(OUT.glob('*-native-matrix.tsv.gz')),*sorted(OUT.glob('*-status-matrix.tsv.gz')),OUT/'analysis-execution-r003.json',OUT/'author-workbook-inspection.json',W/'blobs/sha256/98/98071053e11e1b5a7feaf41d5b76e30cba8e1a7cb2aefdd2287557429054a6b0']
map_inputs=[Q/'inputs/curated-edges.json',OUT/'executed-contrasts.tsv',*[Q/('inputs/primary/'+n) for n in ['PMC6128698-retry.txt','PMC13520134-retry.txt','PMC5414202.xml.txt','PMC8780053.txt']],Q.parent/'q_e835197734394f30/inputs/primary/PMC4925303.txt']
entries=[]
for name in ['executed-contrasts.tsv','panel-measurements.tsv','sample-design.tsv','full-feature-contrasts.tsv.gz','genotype-stiffness-interactions.tsv']:
    entries.append((name,'analyze_mechanics.py','analysis-execution-r003.json',base,'mechanics-'+name.split('.')[0]))
for name in ['result-summary.json','validation.json']:
    entries.append((name,'validate_results.py','validation-execution-r001.json',validation_inputs,'mechanics-'+name.split('.')[0]))
for name in ['intervention-pathway-PMP22-edges.tsv','novelty-audit.json']:
    entries.append((name,'compile_evidence.py','map-execution-r001.json',map_inputs,'mechanics-'+name.split('.')[0]))
if args.first:
    entries=entries[:1]
if args.bundle:
    bundle=json.loads((OUT/'bundle-manifest.json').read_text())
    entries=[('mechanics-evidence.zip','package_evidence.py','package-execution-r001.json',[W/x['workspace_path'] for x in bundle['members']],'mechanics-reproducible-evidence-bundle')]
for name,code,receipt,sources,role in entries:
    target=OUT/name
    rp=REG/(name+'.registration.json')
    if not rp.exists():
        r=json.loads((OUT/receipt).read_text())
        assert r['complete'] and r['exit_code']==0 and r['code_unchanged']
        assert sha(Q/'scripts'/code)==r['code_sha256']
        matches=[x for x in r['outputs'] if Path(x['path']).name==name]
        assert len(matches)==1 and matches[0]['written'] and matches[0]['sha256']==sha(target)
        cmd=['register',str(target),'--question','q_4f573ee10eee421b','--title','PMP22 mechanical replication: '+name,'--summary','Four-study processed-RNA analysis. Environmental transfer, genetic tests and source-curated map remain distinct. No donor, activity-preservation or nascent-initiation claim.','--code',str(Q/'scripts'/code),'--output-role',role,'--parameters',json.dumps({'producer_receipt':receipt,'prediction_lock':'5239371537f3699d2e6a2b0bdd52e7605ddf2c9e11a822b8ada8ed436701f216','scope':'conditional quantitative reanalysis; source-reported and authored evidence typed separately'}),'--reference',obj(OUT/receipt)]
        for path in sorted(set(sources),key=str):
            cmd.extend(['--input',obj(path)])
        reg=bio(cmd)
        rp.write_text(json.dumps(reg,indent=2,allow_nan=False)+'\n')
    else:
        reg=json.loads(rp.read_text())
    assert 'artifact' in reg
    shown=bio(['artifact','show',reg['artifact']])
    assert shown['output_blob']==sha(target) and shown['output_role']==role
    assert any(x['question_id']=='q_4f573ee10eee421b' for x in shown['questions'])
    (REG/(name+'.readback.json')).write_text(json.dumps(shown,indent=2,allow_nan=False)+'\n')
    print(name,reg['artifact'],shown['output_blob'])
