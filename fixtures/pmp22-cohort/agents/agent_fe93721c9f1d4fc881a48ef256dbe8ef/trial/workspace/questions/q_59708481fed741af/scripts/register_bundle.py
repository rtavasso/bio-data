"""Register the verified archive assembly and preserve all declared member inputs."""
import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
bio = str(Path.cwd() / 'bin/bio')

def call(args):
    return json.loads(subprocess.run([bio, *args], check=True, text=True, capture_output=True).stdout)

manifest = json.loads((out / 'bundle-manifest.json').read_text())
inputs = []
for member in manifest['files']:
    path = q / member['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == member['sha256']
    rec = call(['object', 'add', str(path)])
    assert rec['blob'] == member['sha256']
    inputs.append(rec['blob'])
inputs.append(call(['object', 'add', str(out / 'bundle-manifest.json')])['blob'])
inputs.extend(['4905084f5db89ba5bfdcb3d68821eb82e62740bc574b429faecad960237775b7',
               'fe184f9cd2aa618216a51d30d1a9f726b8b284ebb703ed8ff277b98f69e12a57',
               '8b0271c912e5a40eee46fc5328862e7b2f56a3dddd31ef8139e7d5a8ce1069b0',
               'febf649b6685ed045eea6758490f75fd8c5bdd37841a1500481b9888116c29bb',
               'artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a',
               'cc3f098b687c26493f4095548b1f9822259f92ac30f26ef5b5d470b5ec8f924b'])
receipt = json.loads((out / 'bundle-execution-r001.json').read_text())
assert receipt['complete'] and receipt['exit_code'] == 0
for product in receipt['outputs']:
    assert hashlib.sha256(Path(product['path']).read_bytes()).hexdigest() == product['sha256']
reference = call(['object', 'add', str(out / 'bundle-execution-r001.json')])['blob']
args = ['register', str(out / 'EGR2-PMP22-mediation-audit.zip'), '--question', q.name,
        '--title', 'EGR2-PMP22 mediation audit: primary evidence, descriptive RNA counterexample and falsifiable rescue test',
        '--summary', 'Verified archive assembly of agent-curated report, 13 intervention/assay contexts, original-source-checked RNA analysis, samples, scripts, failures and receipts. No eligible selective EGR2 activity/Pmp22-initiation contrast; no mediated fraction estimated.',
        '--code', str(q / 'scripts/build_bundle.py'), '--reference', reference,
        '--output-role', 'mediation-audit-bundle', '--parameters', '{"role":"archive_assembly","independent_replication":false}']
for item in dict.fromkeys(inputs):
    args += ['--input', item]
reg = call(args)
(out / 'registration-bundle.json').write_text(json.dumps(reg, indent=2, allow_nan=False) + '\n')
assert not reg['conflicting_outputs']
back = call(['artifact', 'show', reg['artifact']])
(out / 'readback-bundle.json').write_text(json.dumps(back, indent=2, allow_nan=False) + '\n')
assert back['output_blob'] == hashlib.sha256((out / 'EGR2-PMP22-mediation-audit.zip').read_bytes()).hexdigest()
assert q.name in json.dumps(back['questions'])
print(json.dumps({'artifact': reg['artifact'], 'output_blob': reg['output_blob'], 'verified': True, 'preserved_member_inputs': len(manifest['files'])}))
