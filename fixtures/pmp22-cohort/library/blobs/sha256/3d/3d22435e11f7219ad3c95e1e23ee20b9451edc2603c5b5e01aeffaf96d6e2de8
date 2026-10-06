"""Preserve exact dependencies, register computed screen outputs, and read them back."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
import numpy,scipy
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
out=q/'outputs'
def cli(args):
    r=subprocess.run(['./bin/bio',*args],capture_output=True,text=True)
    if r.returncode: raise RuntimeError((args,r.returncode,r.stdout,r.stderr))
    return json.loads(r.stdout)
def preserve(p,cls='source'):
    result=cli(['object','add',str(p),'--classification',cls]);objects[str(p.relative_to(q))]=result;return result['blob']
receipt=json.loads((out/'screen-execution-r002.json').read_text());assert receipt['complete'] and receipt['exit_code']==0
assert hashlib.sha256((q/'scripts/screen_selectivity.py').read_bytes()).hexdigest()==receipt['code_sha256']
for row in receipt['outputs']:assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256']
screen=json.loads((out/'screen-summary.json').read_text());inputs=list(screen['inputs']);objects={}
paths=[out/'fields-GSE177037-full.json',out/'fields-GSE104324.json',out/'list-GSE104324.json',q/'inputs/panel-spec.json',*sorted(out.glob('fetch-NRG1-*.json'))]
inputs += [preserve(p) for p in paths]
refs=[preserve(out/'screen-execution-r002.json','reference'),preserve(q/'inputs/frozen-prediction.json','reference')]
registrations={}
products={'screen-summary.json':'complete-screen-summary','screen-gene-effects.tsv':'screen-gene-effects','screen-sample-values.tsv':'screen-sample-values','screen-sensitivities.tsv':'screen-robustness'}
for name,role in products.items():
    args=['register',str(out/name),'--question','q_6a3a0a07fa5d4da1','--title',f'Pmp22 intervention selectivity: {role}','--output-role',role,'--code',str(q/'scripts/screen_selectivity.py'),'--parameters',json.dumps({'stage':'exploratory','python':sys.version,'numpy':numpy.__version__,'scipy':scipy.__version__,'panel_spec_sha256':screen['panel_spec_sha256']})]
    for h in inputs:args.extend(['--input',h])
    for h in refs:args.extend(['--reference',h])
    result=cli(args);(out/f'register-{role}.json').write_text(json.dumps(result,indent=2));print(name,result)
    artifact=result['artifact'];verified=cli(['artifact','show',artifact]);(out/f'readback-{role}.json').write_text(json.dumps(verified,indent=2))
    assert verified['output_blob']==hashlib.sha256((out/name).read_bytes()).hexdigest()
    assert any(x['question_id']=='q_6a3a0a07fa5d4da1' and x['relationship']=='produced' for x in verified['questions'])
    registrations[name]={'artifact':artifact,'blob':verified['output_blob'],'verified':True}
(out/'screen-registrations.json').write_text(json.dumps(registrations,indent=2))
(out/'screen-preserved-objects.json').write_text(json.dumps(objects,indent=2))
print('VERIFIED',len(registrations),'outputs; dependency objects',len(objects))
