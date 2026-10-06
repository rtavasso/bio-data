"""Register verified outputs and read exact artifacts back; save every receipt."""
import argparse
import hashlib
import json
import pathlib
import subprocess

Q=pathlib.Path(__file__).resolve().parents[1]
OUT=Q/'outputs'
REG=OUT/'registrations'
REG.mkdir(exist_ok=True)

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def bio(args):
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError(f'{args}: {p.stdout}\n{p.stderr}')
    return json.loads(p.stdout)

def obj(path):
    d=bio(['object','add',str(path)])
    assert d['blob']==digest(path)
    return d['blob']

parser=argparse.ArgumentParser()
parser.add_argument('--first',action='store_true')
parser.add_argument('--bundle',action='store_true')
args=parser.parse_args()
primary=Q/'inputs/primary'
array_sources=[primary/'GSE165206-samples.soft',primary/'PMC8124465.xml',OUT/'decision-array.md']
curated=json.loads((Q/'inputs/curated-evidence.json').read_text())
metadata=json.loads((OUT/'sample-metadata.json').read_text())
audit_sources=sorted({Q/'inputs/curated-evidence.json',OUT/'sample-metadata.json',OUT/'array-summary.json',OUT/'array-all-probes.tsv',*[Q/r['file'] for r in curated],*[primary/r['source'] for r in metadata]},key=str)
entries=[
 ('array-summary.json','analyze_array.py','array-execution-r001.json','array-summary','GSE165206 descriptive stiffness audit; no donor or promoter inference',array_sources),
 ('array-all-probes.tsv','analyze_array.py','array-execution-r001.json','array-full-measured-universe','GSE165206 all measured probes with native values and detection',array_sources),
 ('array-panel.tsv','analyze_array.py','array-execution-r001.json','array-regulator-panel','GSE165206 prespecified PMP22 EGR2 state panel, unreplicated contrasts',array_sources),
 ('array-panel-annotations.tsv','analyze_array.py','array-execution-r001.json','array-panel-annotation','Literal RefSeq annotation and SOFT locators for regulatory panel',array_sources),
 ('assay-eligibility.tsv','validate_and_compile.py','validation-execution-r002.json','assay-eligibility','Extrinsic PMP22 source-located assay and mediation eligibility',audit_sources),
 ('sample-eligibility.tsv','validate_and_compile.py','validation-execution-r002.json','sample-eligibility','Extrinsic PMP22 sample identities and assay eligibility',audit_sources),
 ('validation.json','validate_and_compile.py','validation-execution-r002.json','validation','Source-row and derived-contrast verification with platform-only list',audit_sources),
]
if args.first:
    entries=entries[:1]
elif args.bundle:
    manifest=json.loads((OUT/'bundle-manifest.json').read_text())
    members=[Q/r['path'] for r in manifest['members']]
    entries=[('extrinsic-evidence.zip','package_evidence.py','package-execution-r001.json','evidence-bundle','PMP22 extrinsic mediation map, array audit, sources and proposed factorial test',members)]
for filename,code,receipt_name,role,title,sources in entries:
    target=OUT/filename
    receipt_path=REG/(filename+'.registration.json')
    if receipt_path.exists():
        reg=json.loads(receipt_path.read_text())
    else:
        execution=json.loads((OUT/receipt_name).read_text())
        assert execution['exit_code']==0 and execution['complete'] and execution['code_unchanged']
        assert digest(Q/'scripts'/code)==execution['code_sha256']
        matched=[o for o in execution['outputs'] if pathlib.Path(o['path']).name==filename]
        assert len(matched)==1 and matched[0]['written'] and matched[0]['sha256']==digest(target)
        command=['register',str(target),'--question','q_e835197734394f30','--title',title,'--output-role',role,'--code',str(Q/'scripts'/code),'--parameters',json.dumps({'producer_receipt':receipt_name,'scope':'descriptive bounded audit; proposed experiment not performed'}),'--reference',obj(OUT/receipt_name)]
        for path in sources:
            command+=['--input',obj(path)]
        for transport in sorted(primary.glob('transport-r*.json')):
            command+=['--reference',obj(transport)]
        reg=bio(command)
        receipt_path.write_text(json.dumps(reg,indent=2,allow_nan=False)+'\n')
    assert 'artifact' in reg,reg
    shown=bio(['artifact','show',reg['artifact']])
    assert shown['output_blob']==digest(target)
    assert shown['output_role']==role
    assert any(x['question_id']=='q_e835197734394f30' for x in shown['questions'])
    (REG/(filename+'.readback.json')).write_text(json.dumps(shown,indent=2,allow_nan=False)+'\n')
    print(filename,reg['artifact'],shown['output_blob'])
