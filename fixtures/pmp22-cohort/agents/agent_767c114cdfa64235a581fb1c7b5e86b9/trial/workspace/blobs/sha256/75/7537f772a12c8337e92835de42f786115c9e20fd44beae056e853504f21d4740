"""Validate producing receipts, register each output once, and read back exact artifacts."""
import hashlib
import json
from pathlib import Path
import subprocess

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
reg = out / 'registrations-r003'
reg.mkdir(exist_ok=True)

def cli(args):
    p = subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

receiptpath = out / 'execution-audit-r003.json'
r = json.loads(receiptpath.read_text())
assert r['complete'] and r['exit_code']==0 and r['code_unchanged']
assert sha(Path(r['producer']))==r['code_sha256']
for item in r['outputs']:
    assert item['written'] and sha(Path(item['path']))==item['sha256']
    p = Path(item['path'])
    if p.suffix=='.json':
        json.loads(p.read_text(),parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
receiptblob = cli(['object','add',str(receiptpath)])['blob']
manifest = json.loads((q / 'inputs/analysis-manifest-r003.json').read_text())
manifestblob = cli(['object','add',str(q / 'inputs/analysis-manifest-r003.json')])['blob']
inputblobs = list(dict.fromkeys([manifestblob]+[x['blob'] for x in manifest['objects']]))
roles = {'rna-fate-audit.json':'integrated-audit','sample-assay-eligibility.json':'sample-eligibility',
         'published-measurements.json':'published-table-extraction','evidence-matrix.tsv':'evidence-matrix','assay-matrix.tsv':'assay-matrix'}
for filename,role in roles.items():
    p = out / filename
    saved = reg / (filename+'.registration.json')
    if saved.exists():
        result = json.loads(saved.read_text())
    else:
        args=['register',str(p),'--question',q.name,'--title','PMP22 RNA fate: '+role,
              '--summary','Source-audited mature RNA fate, human UTR evidence, route limits and falsifier; not independent biological replication',
              '--code',str(q/'scripts/compile_audit.py'),'--parameters',json.dumps({'scope':'bounded-source-audit','rate_fit':False}),
              '--reference',receiptblob,'--output-role',role]
        for h in inputblobs:
            args += ['--input',h]
        result=cli(args)
        saved.write_text(json.dumps(result,indent=2,allow_nan=False))
    assert isinstance(result['artifact'],str) and result['output_blob']==sha(p)
    check=cli(['artifact','show',result['artifact']])
    (reg / (filename+'.readback.json')).write_text(json.dumps(check,indent=2,allow_nan=False))
    assert result['output_blob'] in json.dumps(check)
    print(filename, result['artifact'], result['output_blob'])
