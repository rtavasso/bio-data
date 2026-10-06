"""Register audited outputs and verify each exact catalog record after writing."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

Q = Path(__file__).resolve().parents[1]
ROOT = Q.parents[2]
REG = Q / 'outputs/registrations'
REG.mkdir(exist_ok=True)


def bio(*args):
    p = subprocess.run(['./bin/bio', *map(str, args)], cwd=ROOT,
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)


def store(path):
    r = bio('object', 'add', path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == r['blob']
    return r['blob']


def save(path, obj):
    with path.open('x') as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.write('\n')


ap = argparse.ArgumentParser()
ap.add_argument('mode', choices=['first', 'rest'])
args = ap.parse_args()
receipt_path = Q / 'outputs/execution-r002.json'
receipt = json.loads(receipt_path.read_text())
assert receipt['exit_code'] == 0 and receipt['complete'] and receipt['code_unchanged']
producer = Q / 'scripts/audit_human_dosage.py'
assert store(producer) == receipt['code_sha256']
receipt_hash = store(receipt_path)
input_manifest = json.loads((Q / 'inputs/immutable-inputs.json').read_text())
validation = json.loads((Q / 'outputs/r002/audit-validation.json').read_text())
inputs = [{'blob': r['blob'], 'role': 'annotation' if r['relative_path'].endswith('evidence-annotations.json') else 'source_evidence',
           'selector': {'source_file': r['relative_path']}, 'source_identity': ''}
          for r in input_manifest['inputs']]
common = {'inputs': inputs, 'code': [receipt['code_sha256']],
          'parameters': {'revision': 'r002', 'analysis': 'descriptive source verification; no donor-inferential statistics'},
          'references': [receipt_hash, store(Q / 'inputs/immutable-inputs.json')],
          'environment': {k: validation[k] for k in ['python', 'openpyxl', 'platform']},
          'command': receipt['argv']}
products = [
    ('within-background-summary.json', 'Human PMP22 within-background RNA, total protein and structural-overlap verification', 'endpoint_summary_json'),
    ('human-evidence-matrix.json', 'Human PMP22 donor, copy-number and endpoint applicability matrix', 'evidence_matrix_json'),
    ('human-evidence-matrix.tsv', 'Human PMP22 endpoint applicability matrix: tabular form', 'evidence_matrix_tsv'),
    ('within-background-values.tsv', 'Native PMP22 intervention values with exact worksheet cell locators', 'endpoint_values_tsv'),
    ('within-background-summary.tsv', 'Human PMP22 within-background descriptive ratios: tabular form', 'endpoint_summary_tsv'),
    ('GSE7423-donor-channel-map.tsv', 'GSE7423 donor and mutation-class channel audit', 'geo_sample_map_tsv'),
    ('GSE7423-design-summary.json', 'GSE7423 dosage-donor non-identifiability audit', 'geo_design_json'),
    ('audit-validation.json', 'Human PMP22 audit input/output validation', 'validation_json')]
selected = products[:1] if args.mode == 'first' else products[1:]
for name, title, role in selected:
    path = Q / 'outputs/r002' / name
    expected = next(o for o in receipt['outputs'] if Path(o['path']).name == name)
    assert expected['written']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected['sha256']
    manifest = {'title': title,
                'summary': 'Bounded human PMP22 dosage audit. Nine annotated contexts; one retrospective within-background numerical verification. Counts of clones, samples, cells and donors remain distinct.',
                'derivation': common, 'output_role': role, 'kind': 'file',
                'limitations': ['No calibrated genomic-copy-number to functional-protein curve identified.',
                                'No independent biological replication or new donor-level p-values.',
                                'Source annotations are researcher judgments, not automated inference.']}
    mp = REG / (name + '.manifest.json')
    save(mp, manifest)
    result = bio('register', path, '--manifest', mp, '--question', Q.name)
    save(REG / (name + '.registration.json'), result)
    assert result['output_blob'] == expected['sha256']
    assert not result['conflicting_outputs']
    record = bio('artifact', 'show', result['artifact'])
    save(REG / (name + '.readback.json'), record)
    assert record['output_blob'] == result['output_blob']
    assert record['manifest']['derivation']['command'] == receipt['argv']
    assert Path(record['path']).read_bytes() == path.read_bytes()
    print(json.dumps({'file': name, 'artifact': result['artifact'], 'verified': True}))
