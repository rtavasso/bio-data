import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
bio = str(Path.cwd() / 'bin/bio')
def call(args):
    return json.loads(subprocess.run([bio, *args], capture_output=True, text=True, check=True).stdout)
receipt = json.loads((out / 'correction-execution-r001.json').read_text())
assert receipt['complete'] and receipt['exit_code'] == 0 and receipt['code_unchanged']
for product in receipt['outputs']:
    assert hashlib.sha256(Path(product['path']).read_bytes()).hexdigest() == product['sha256']
inputs = ['artifact_0e97fd2932f209820af010da8872510c1c33f17a25a2eb8605f3969fa43f5bc6']
for rel in ['LABBOOK.md', 'outputs/REPORT.md', 'inputs/browser-checks.json', 'outputs/provenance-correction.json']:
    inputs.append(call(['object', 'add', str(q / rel)])['blob'])
ref = call(['object', 'add', str(out / 'correction-execution-r001.json')])['blob']
args = ['register', str(out / 'EGR2-PMP22-mediation-audit.r002.zip'), '--question', q.name,
        '--title', 'EGR2-PMP22 mediation audit r002: browser attribution retracted; scientific results unchanged',
        '--summary', 'Corrected archive preserving actual HTTP and immutable-source provenance. All numerical RNA, intervention/eligibility and rescue-design outputs byte-identical to r001. Unsupported browser ledger fully withdrawn.',
        '--code', str(q / 'scripts/build_corrected_bundle.py'), '--reference', ref,
        '--output-role', 'mediation-audit-bundle-corrected', '--parameters', '{"revision":2,"browser_claim_withdrawn":true,"scientific_results_unchanged":true}']
for inp in inputs:
    args += ['--input', inp]
reg = call(args)
(out / 'registration-corrected-bundle.json').write_text(json.dumps(reg, indent=2, allow_nan=False) + '\n')
assert not reg['conflicting_outputs']
back = call(['artifact', 'show', reg['artifact']])
(out / 'readback-corrected-bundle.json').write_text(json.dumps(back, indent=2, allow_nan=False) + '\n')
assert back['output_blob'] == hashlib.sha256((out / 'EGR2-PMP22-mediation-audit.r002.zip').read_bytes()).hexdigest()
assert q.name in json.dumps(back['questions'])
print(json.dumps({'artifact': reg['artifact'], 'output_blob': reg['output_blob'], 'verified': True}))
