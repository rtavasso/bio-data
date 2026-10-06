"""Register setup products with real local producer provenance; no scientific computation."""
import hashlib
import json
import subprocess
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
R = OUT / 'receipts'


def cli(*args):
    return json.loads(subprocess.check_output(['./bin/bio', *map(str, args)], text=True))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


execution = json.loads((OUT / 'setup-assembly-execution-r001.json').read_text())
assert execution['complete'] and execution['exit_code'] == 0 and execution['code_unchanged']
receipt_hash = json.loads((R / 'assembly-receipt-object.json').read_text())['blob']
input_hash = json.loads((R / 'handoff-inputs-object.json').read_text())['blob']
parameters = {'scope': 'cohort setup; no biological analysis', 'question': Q.name,
              'seed_post': 'post_9d25fbe9084740baba1e8b48870d434e',
              'charter_post': 'post_569bb436329e46828ed286a26425ab03', 'revision': 1}
products = [('cohort.json', 'cohort-design', 'cohort-registration.json', 'PMP22 ten-member cohort: registered roster and proposed relationships'),
            ('COHORT.md', 'cohort-readable-roster', 'roster-registration.json', 'PMP22 cohort readable roster and proposed exchanges'),
            ('setup-verification.json', 'cohort-unlaunched-verification', 'verification-registration.json', 'Actual board verification: ten pending, zero child executions'),
            ('cohort-handoff.zip', 'cohort-handoff-bundle', 'bundle-registration.json', 'PMP22 cohort handoff: matching briefs, board receipts and setup provenance')]
registered = []
for filename, role, receipt_name, title in products:
    output = OUT / filename
    actual_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    assert any(o['sha256'] == actual_hash and o['path'] == str(output) and o['written'] for o in execution['outputs'])
    path = R / receipt_name
    if path.exists():
        receipt = json.loads(path.read_text())
    else:
        receipt = cli('register', output, '--question', Q.name, '--title', title,
                      '--summary', 'Operational setup/handoff only. Exactly ten fresh registered members, one pending task each, zero sessions/attempts. Proposed relationships are not observed behavior.',
                      '--input', input_hash, '--code', Q / 'scripts/verify_and_assemble.py',
                      '--reference', receipt_hash, '--parameters', json.dumps(parameters), '--output-role', role)
        save(path, receipt)
    assert receipt['output_blob'] == actual_hash and not receipt['conflicting_outputs']
    actual = cli('artifact', 'show', receipt['artifact'])
    save(R / (role + '.artifact-readback.json'), actual)
    assert actual['id'] == receipt['artifact'] and actual['output_blob'] == actual_hash
    assert actual['manifest']['output']['name'] == filename and actual['output_role'] == role
    assert Q.name in json.dumps(actual['questions'])
    assert receipt_hash in actual['manifest']['derivation']['references']
    registered.append({'file': filename, 'artifact': receipt['artifact'], 'output_blob': actual_hash, 'role': role})
    print(filename, receipt['artifact'], 'registered/readback-verified')
save(OUT / 'registered-outputs.json', registered)
