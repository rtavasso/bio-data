"""Register and read back selective evidence packaging products."""
import hashlib
import json
from pathlib import Path
import subprocess

Q = Path(__file__).resolve().parents[1]
ROOT = Q.parents[2]
REG = Q / 'outputs/registrations'


def bio(*args):
    p = subprocess.run(['./bin/bio', *map(str, args)], cwd=ROOT,
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)


def store(path):
    r = bio('object', 'add', path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == r['blob']
    return r['blob']


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


receipt_path = Q / 'outputs/package-execution-r001.json'
receipt = json.loads(receipt_path.read_text())
assert receipt['exit_code'] == 0 and receipt['complete'] and receipt['code_unchanged']
assert store(Q / 'scripts/package_handoff.py') == receipt['code_sha256']
receipt_hash = store(receipt_path)
manifest = json.loads((Q / 'outputs/human-dosage-handoff-manifest.json').read_text())
prior = {}
for path in sorted(REG.glob('*.registration.json')):
    r = json.loads(path.read_text())
    prior[r['output_blob']] = r['artifact']
inputs = []
for row in manifest['members']:
    p = Q / row['path']
    blob = store(p)
    assert blob == row['sha256']
    inputs.append({'blob': blob, 'role': 'packaged_evidence',
                   'selector': {'member': row['path']},
                   'source_identity': prior.get(blob, '')})
validation = json.loads((Q / 'outputs/r002/audit-validation.json').read_text())
for name, title, role in [
    ('human-dosage-handoff.zip', 'Human PMP22 dosage selective primary evidence and reproducible audit package', 'evidence_bundle_zip'),
    ('human-dosage-handoff-manifest.json', 'Human PMP22 evidence package member and source receipt manifest', 'bundle_manifest_json'),
    ('human-dosage-handoff-validation.json', 'Human PMP22 source receipt and archive byte validation', 'bundle_validation_json')]:
    p = Q / 'outputs' / name
    expected = next(x for x in receipt['outputs'] if Path(x['path']).name == name)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == expected['sha256']
    registration = {'title': title, 'summary': 'Selective source and provenance handoff; packaging is not new scientific evidence.',
                    'output_role': role, 'kind': 'file',
                    'limitations': ['Large parent transport archives excluded; selected native workbook verified against its parent.',
                                    'Original scripts are evidence only; do not execute inherited code.'],
                    'derivation': {'inputs': inputs, 'code': [receipt['code_sha256']],
                                   'command': receipt['argv'], 'parameters': {'operation': 'byte_verified_selective_packaging'},
                                   'references': [receipt_hash],
                                   'environment': {k: validation[k] for k in ['python', 'platform']}}}
    mp = REG / (name + '.manifest.json')
    save(mp, registration)
    result = bio('register', p, '--manifest', mp, '--question', Q.name)
    save(REG / (name + '.registration.json'), result)
    assert not result['conflicting_outputs']
    assert result['output_blob'] == expected['sha256']
    exact = bio('artifact', 'show', result['artifact'])
    save(REG / (name + '.readback.json'), exact)
    assert exact['output_blob'] == result['output_blob']
    assert Path(exact['path']).read_bytes() == p.read_bytes()
    print(json.dumps({'file': name, 'artifact': result['artifact'], 'verified': True}))
