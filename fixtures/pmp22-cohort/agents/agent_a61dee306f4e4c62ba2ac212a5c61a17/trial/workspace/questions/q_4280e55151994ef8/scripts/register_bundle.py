"""Register the verified packaging output without rerunning any science."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs'


def cli(*args):
    p = subprocess.run(['./bin/bio', *map(str, args)], text=True, capture_output=True, check=True)
    return json.loads(p.stdout)


def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


receipt = json.loads((OUT/'bundle-execution-r001.json').read_text())
assert receipt['complete'] and receipt['code_unchanged'] and receipt['exit_code'] == 0
assert sha(ROOT/'scripts'/'bundle_audit.py') == receipt['code_sha256']
for output in receipt['outputs']:
    assert output['written'] and sha(OUT/Path(output['path']).name) == output['sha256']
objects = {}
for name in ['bundle-manifest.json','bundle-validation.json','bundle-execution-r001.json']:
    obj = cli('object','add',OUT/name,'--classification','reference')
    assert obj['blob'] == sha(OUT/name)
    objects[name] = obj
    save('bundle-object-receipts.json', objects)
regs = json.loads((OUT/'registrations.json').read_text())
args = ['register',OUT/'stress-audit-bundle.zip','--question','q_4280e55151994ef8',
        '--title','PMP22 stress audit: selected native sources, numerical outputs and actual receipts',
        '--summary','Packaging only; no new scientific execution. Relative footprints, matched fractions, TE eligibility and explicit synthesis blockers.',
        '--output-role','stress-audit-bundle','--code',ROOT/'scripts'/'bundle_audit.py',
        '--parameters',json.dumps({'assembly':'selected own question files','manifest_blob':objects['bundle-manifest.json']['blob']})]
for reg in regs.values():
    args += ['--input',reg['artifact']]
args += ['--input',objects['bundle-manifest.json']['blob']]
for name in ['bundle-validation.json','bundle-execution-r001.json']:
    args += ['--reference',objects[name]['blob']]
registration = cli(*args)
save('bundle-registration.json',registration)
assert not registration['conflicting_outputs'] and registration['output_blob'] == sha(OUT/'stress-audit-bundle.zip')
shown = cli('artifact','show',registration['artifact'])
save('bundle-artifact-readback.json',shown)
assert shown['id'] == registration['artifact'] and shown['output_blob'] == registration['output_blob']
assert any(x['question_id']=='q_4280e55151994ef8' and x['relationship']=='produced' for x in shown['questions'])
print(json.dumps(registration,indent=2))
