"""Register useful final products with exact dependencies and producer receipts; verify readbacks."""
import hashlib,json,os,subprocess
from pathlib import Path
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';O=Q/'outputs';P=Q/'inputs/public'
assert json.loads((O/'final-validation.json').read_text())['passed']
objects={};registry=json.loads((O/'screen-registrations.json').read_text())
def cli(args):
    r=subprocess.run(['./bin/bio',*args],capture_output=True,text=True)
    if r.returncode:raise RuntimeError((args,r.returncode,r.stdout,r.stderr))
    return json.loads(r.stdout)
def obj(path,classification='reference'):
    path=Path(path);key=str(path)
    if key not in objects:objects[key]=cli(['object','add',str(path),'--classification',classification])
    return objects[key]['blob']
def dep(path):
    path=Path(path)
    if path.parent==O and path.name in registry:return registry[path.name]['artifact']
    return obj(path,'reference')
def register_stage(stage,producer,receipt,products,dependencies,native=(),references=()):
    r=json.loads((O/receipt).read_text());assert r['complete'] and r['exit_code']==0
    assert hashlib.sha256((Q/'scripts'/producer).read_bytes()).hexdigest()==r['code_sha256']
    inputs=list(native)+[dep(p) for p in dependencies];refs=[obj(O/receipt)]+[obj(p) for p in references]
    for filename,role in products.items():
        p=O/filename;expected=hashlib.sha256(p.read_bytes()).hexdigest();assert any(v['sha256']==expected and Path(v['path']).name==filename for v in r['outputs'])
        args=['register',str(p),'--question','q_6a3a0a07fa5d4da1','--title',f'Pmp22 across-perturbation audit: {role}','--output-role',role,'--code',str(Q/'scripts'/producer),'--parameters',json.dumps({'stage':stage,'native_scale_preserved':True,'scientific_status':'see output eligibility, replication and uncertainty fields'})]
        for h in sorted(set(inputs)):args.extend(['--input',h])
        for h in refs:args.extend(['--reference',h])
        result=cli(args);(O/f'register-final-{role}.json').write_text(json.dumps(result,indent=2))
        readback=cli(['artifact','show',result['artifact']]);(O/f'readback-final-{role}.json').write_text(json.dumps(readback,indent=2))
        assert readback['output_blob']==expected and any(x['question_id']=='q_6a3a0a07fa5d4da1' and x['relationship']=='produced' for x in readback['questions'])
        registry[filename]={'artifact':result['artifact'],'blob':expected,'verified':True};print(filename,result['artifact'])
        (O/'all-registrations.json').write_text(json.dumps(registry,indent=2));(O/'final-preserved-objects.json').write_text(json.dumps(objects,indent=2))
# Preserve received native public scientific files as source objects, together with receipt dependencies.
array=json.loads((O/'array-summary.json').read_text());arraydeps=[Q/'inputs/panel-spec.json',Q/'inputs/array-spec.json'];arraynative=[]
for name in array['inputs']:
    path=P/name;arraynative.append(obj(path,'source'));arraydeps.append(path.with_name(path.name+'.receipt.json'))
register_stage('exploratory arrays','analyze_arrays.py','array-execution-r003.json',{'array-summary.json':'array-summary','array-gene-effects.tsv':'array-gene-effects','array-probe-effects.tsv':'array-probe-effects','array-sample-values.tsv':'array-sample-values','array-sensitivities.tsv':'array-robustness','array-annotation-mismatches.json':'array-native-name-failures'},arraydeps,arraynative,[P/'GSE163132-quick.txt',P/'GSM4972426-quick.txt',P/'E-MEXP-3491.idf.txt',P/'PMC3669361.xml'])
v=json.loads((O/'validation-summary.json').read_text());vdeps=[O/'fields-GSE108231.json',O/'fetch-GSE108231.json',Q/'inputs/panel-spec.json',Q/'inputs/frozen-prediction.json',Q/'inputs/validation-selection.json'];vnative=[v['native_input']]
for gene in v['annotation']:
    path=P/f'ensembl-mouse-{gene}.json';vnative.append(obj(path,'source'));vdeps.append(path.with_name(path.name+'.receipt.json'))
register_stage('frozen independent injury prediction and exploratory Raptor contrasts','validate_injury_prediction.py','validation-execution-r001.json',{'validation-summary.json':'independent-validation-summary','validation-gene-effects.tsv':'independent-validation-genes','validation-sample-values.tsv':'independent-validation-samples','validation-sensitivities.tsv':'independent-validation-robustness'},vdeps,vnative,[P/'PMC5956991.xml',P/'PMC5956991.xml.receipt.json'])
rdeps=[O/f'{s}-{suffix}' for s in ['screen','array','validation'] for suffix in ['summary.json','gene-effects.tsv','sensitivities.tsv']]+[O/'promoter-peer-answer.json',Q.parent/'q_ec00fef1019a4c6f/inputs/public/repair.xml',Q/'inputs/primary/PMC5960709.xml',Q/'inputs/primary/PMC9469140.xml',P/'PMC3669361.xml',P/'PMC5956991.xml']
register_stage('retrospective comparator sensitivity and bounded main-text novelty audit','summarize_robustness.py','robustness-execution-r001.json',{'robustness-and-core5.json':'retrospective-panel-dependence','novelty-text-audit.json':'source-novelty-audit'},rdeps)
r=json.loads((O/'rbp-coverage-summary.json').read_text());rbpdeps=[O/'fields-GSE177037-full.json',O/'fields-GSE104324.json',O/'list-GSE104324.json',*sorted(O.glob('fetch-NRG1-*.json'))]
register_stage('retrospective peer transfer-eligibility check','peer_rbp_coverage.py','rbp-coverage-execution-r002.json',{'rbp-coverage-summary.json':'peer-rbp-coverage-summary','rbp-coverage-samples.tsv':'peer-rbp-coverage-samples'},rbpdeps,list(r['inputs']),[O/'inbox-post-ea149c.json'])
register_stage('ranked source-aware contrast resource','build_contrast_resource.py','resource-execution-r002.json',{'ranked-candidates.tsv':'ranked-selectivity-candidates','experiment-contrasts.tsv':'experiment-eligibility-resource','contrast-resource-summary.json':'contrast-resource-summary'},[Q/'inputs/experiment-judgments.json',O/'robustness-and-core5.json',O/'screen-summary.json',O/'array-summary.json',O/'validation-summary.json'],references=[Q/'inputs/considered-contexts.json',O/'final-validation.json',Q/'inputs/panel-spec.json',Q/'inputs/frozen-prediction.json'])
print('VERIFIED_REGISTERED_PRODUCTS',len(registry))
