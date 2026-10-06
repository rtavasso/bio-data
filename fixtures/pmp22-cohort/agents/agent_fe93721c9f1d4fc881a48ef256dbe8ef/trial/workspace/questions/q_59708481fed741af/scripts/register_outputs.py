"""Register successful computed outputs and verify exact artifact readbacks."""
import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
bio = Path.cwd() / 'bin/bio'

def call(args):
    p = subprocess.run([str(bio), *args], check=True, capture_output=True, text=True)
    return json.loads(p.stdout)

def preserve(path):
    return call(['object', 'add', str(path)])['blob']

first = json.loads((out / 'registration-rna.json').read_text())
assert first['artifact'] and not first['conflicting_outputs']
assert first['output_blob'] == hashlib.sha256((out / 'GSE201623-audit.json').read_bytes()).hexdigest()
readback = call(['artifact', 'show', first['artifact']])
(out / 'readback-rna.json').write_text(json.dumps(readback, indent=2, allow_nan=False) + '\n')
assert readback['output_blob'] == first['output_blob']
assert q.name in json.dumps(readback['questions'])
receipt_blob = preserve(out / 'audit-execution-r001.json')
inputs = ['8d283c25759031d6ca1f471c042af64742bc96d90075830370738b51533054b0',
          'c1038348c4c8d227d3279550c9d3c2bbc5b8d7967825996400bef5746a6486ab',
          first['artifact'], '4905084f5db89ba5bfdcb3d68821eb82e62740bc574b429faecad960237775b7',
          'fe184f9cd2aa618216a51d30d1a9f726b8b284ebb703ed8ff277b98f69e12a57',
          '8b0271c912e5a40eee46fc5328862e7b2f56a3dddd31ef8139e7d5a8ce1069b0',
          'febf649b6685ed045eea6758490f75fd8c5bdd37841a1500481b9888116c29bb']
products = [('intervention-by-endpoint.tsv', 'intervention-endpoint-table'),
            ('assay-eligibility.json', 'assay-eligibility'),
            ('mediation-audit.json', 'mediation-audit')]
registered = [{'file': 'GSE201623-audit.json', **first}]
for name, role in products:
    args = ['register', str(out / name), '--question', q.name,
            '--title', 'EGR2 persistence / PMP22 mediation audit: ' + role,
            '--summary', 'Agent-curated primary-source evidence and explicit eligibility; no matched EGR2 activity/Pmp22 initiation rescue. No protein half-life or mediated fraction estimated.',
            '--output-role', role, '--code', str(q / 'scripts/build_audit.py'), '--reference', receipt_blob,
            '--parameters', json.dumps({'type': 'validated_agent_curated_evidence', 'quantitative_mediation': None})]
    for inp in inputs:
        args.extend(['--input', inp])
    receipt = call(args)
    (out / f'registration-{role}.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    assert not receipt['conflicting_outputs']
    expected = hashlib.sha256((out / name).read_bytes()).hexdigest()
    assert receipt['output_blob'] == expected
    back = call(['artifact', 'show', receipt['artifact']])
    (out / f'readback-{role}.json').write_text(json.dumps(back, indent=2, allow_nan=False) + '\n')
    assert back['output_blob'] == expected and q.name in json.dumps(back['questions'])
    registered.append({'file': name, **receipt})
(out / 'registrations.json').write_text(json.dumps(registered, indent=2, allow_nan=False) + '\n')
print(json.dumps([{'file': r['file'], 'artifact': r['artifact'], 'verified': True} for r in registered]))
