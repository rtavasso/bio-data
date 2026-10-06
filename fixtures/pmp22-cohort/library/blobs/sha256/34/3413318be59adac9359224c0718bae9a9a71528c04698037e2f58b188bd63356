"""Store immutable local inputs and register validated outputs, persisting every receipt."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs'
Q = 'q_4280e55151994ef8'


def cli(*args):
    proc = subprocess.run(['./bin/bio', *map(str,args)], check=True, text=True, capture_output=True)
    return json.loads(proc.stdout)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


store = OUT/'stored-inputs.json'
if store.exists():
    saved = json.loads(store.read_text())
else:
    saved = {}
selected = [ROOT/'inputs'/x for x in ['analysis-plan-r001.json','analysis-plan-r002-addendum.json','context-judgments.json']]
selected += [p for p in (ROOT/'inputs'/'public').iterdir() if p.name.endswith(('.soft','.gz','.xml','.receipt.json'))]
selected += [OUT/x for x in ['execution-r002.json','compilation-execution-r001.json','source-locators.json']]
for p in sorted(selected):
    key = str(p.relative_to(ROOT))
    if key not in saved:
        rec = cli('object','add',p,'--classification','source' if key.startswith('inputs/') else 'reference')
        assert rec['blob'] == sha(p)
        saved[key] = rec
        store.write_text(json.dumps(saved,indent=2,allow_nan=False)+'\n')

inputs = [v['blob'] for k,v in saved.items() if k.startswith('inputs/') and not k.endswith('.receipt.json')]
refs = [v['blob'] for k,v in saved.items() if k.endswith('.receipt.json') or k.startswith('outputs/')]
registration_path = OUT/'registrations.json'
registrations = json.loads(registration_path.read_text()) if registration_path.exists() else {}
items = [
    ('stress-audit-summary.json','PMP22 stress-source replication: relative footprints and matched fractions','stress-audit-summary','analyze_stress.py','execution-r002.json'),
    ('sample-assay-eligibility.tsv','PMP22 stress sample and assay map: 53 source labels','sample-assay-eligibility','analyze_stress.py','execution-r002.json'),
    ('stress-context-replication-matrix.json','PMP22 six-context stress replication and endpoint eligibility','stress-context-matrix','compile_audit.py','compilation-execution-r001.json'),
    ('selective-translation-blocker.json','PMP22 selective-synthesis test: source-specific blockers and discriminating measurements','selective-translation-blocker','compile_audit.py','compilation-execution-r001.json'),
    ('source-locators.json','PMP22 stress sources: actual HTTP receipts, hashes and content eligibility','source-locators','analyze_stress.py','execution-r002.json'),
    ('compilation-validation.json','PMP22 stress audit exact-source validation','validation','compile_audit.py','compilation-execution-r001.json')]
if sys.argv[1] == 'first':
    items = items[:1]
for name,title,role,code,receipt_name in items:
    if name in registrations:
        continue
    receipt = json.loads((OUT/receipt_name).read_text())
    assert receipt['complete'] and receipt['exit_code']==0
    expected = next(x for x in receipt['outputs'] if Path(x['path']).name==name)
    assert expected['sha256'] == sha(OUT/name)
    args = ['register', OUT/name, '--question',Q,'--title',title,'--output-role',role,
            '--code',ROOT/'scripts'/code,'--parameters',json.dumps({'retrospective':True,'source_calibration':'not_absolute','version':1})]
    for h in inputs:
        args += ['--input',h]
    if code == 'compile_audit.py':
        args += ['--input',registrations['stress-audit-summary.json']['artifact']]
    for h in refs:
        args += ['--reference',h]
    rec = cli(*args)
    registrations[name]=rec
    registration_path.write_text(json.dumps(registrations,indent=2,allow_nan=False)+'\n')
    assert rec['output_blob']==sha(OUT/name)
    shown = cli('artifact','show',rec['artifact'])
    (OUT/(name+'.artifact-readback.json')).write_text(json.dumps(shown,indent=2,allow_nan=False)+'\n')
    assert shown['output_blob']==rec['output_blob'] and shown['id']==rec['artifact']
    print(name, json.dumps(rec),flush=True)
