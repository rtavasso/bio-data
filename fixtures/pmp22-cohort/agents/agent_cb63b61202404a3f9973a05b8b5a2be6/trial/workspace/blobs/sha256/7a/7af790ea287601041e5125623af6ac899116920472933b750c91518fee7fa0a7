"""Validate saved producer results and preserve exact registration dependencies."""
import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path

Q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_90f4fed27b7e4793'
O = Q / 'outputs'
R = O / 'registration'
R.mkdir(exist_ok=True)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def reject(value):
    raise ValueError('Non-finite JSON token: ' + value)


def load(path):
    return json.loads(Path(path).read_text(), parse_constant=reject)


def preserve(path, classification='source'):
    path = Path(path)
    h = sha(path)
    receipt_path = R / ('object-' + h + '.json')
    if receipt_path.exists():
        result = load(receipt_path)
    else:
        proc = subprocess.run(['./bin/bio', 'object', 'add', str(path), '--classification', classification],
                              capture_output=True, text=True, check=True)
        result = json.loads(proc.stdout)
        receipt_path.write_text(json.dumps(result, indent=2, allow_nan=False))
    assert result['blob'] == h
    assert sha(result['path']) == h
    return h


receipt = load(O / 'audit-execution-r003.json')
assert receipt['exit_code'] == 0 and receipt['complete'] and receipt['code_unchanged']
assert sha(receipt['producer']) == receipt['code_sha256']
for output in receipt['outputs']:
    assert output['written'] and sha(output['path']) == output['sha256']
audit = load(O / 'causal-evidence-audit.json')
inputs = load(O / 'audit-inputs.json')
assert audit['inputs'] == inputs
assert len(audit['curation']['evidence']) == 10
assert all(not r['pmp22_mediation_eligible'] for r in audit['curation']['evidence'])
assert len(audit['samples']) == 16
with (O / 'locked-panel-eligibility.tsv').open() as f:
    eligibility = list(csv.DictReader(f, delimiter='\t'))
assert len(eligibility) == 52
failed = [r for r in eligibility if r['eligible'] == 'False']
assert len(failed) == 4 and all(r['gene'] == 'Osgin1' and r['measurement_status'] == 'measured' for r in failed)
assert audit['prior_eligibility_verification']['native_selected_count_cells_verified'] == 104
assert audit['prior_eligibility_verification']['original_status'] == 'untestable'
assert audit['prior_eligibility_verification']['posthoc_status'] == 'retrospective_exploratory_not_validation'
with (O / 'epistasis-decision-table.tsv').open() as f:
    decisions = list(csv.DictReader(f, delimiter='\t'))
assert decisions == audit['epistasis_plan']['rows'] and len(decisions) == 7
for item in inputs:
    assert sha(item['path']) == item['sha256']
validation = {'status': 'passed', 'producer_receipt_sha256': sha(O / 'audit-execution-r003.json'),
              'producer_sha256': receipt['code_sha256'], 'checks': {
                  'output_hashes': len(receipt['outputs']), 'input_hashes': len(inputs),
                  'source_assessments': 10, 'sample_records': 16, 'eligibility_rows': 52,
                  'native_count_cells': 104, 'epistasis_cases': 7,
                  'Osgin1_measured_but_ineligible': True, 'original_lock_not_rescued': True,
                  'no_eligible_PMP22_mediation_design_claimed': True},
              'scope': 'Integrity and logical consistency; not independent experimental validation of scientific interpretations'}
(O / 'audit-validation.json').write_text(json.dumps(validation, indent=2, allow_nan=False))

objects = []
for item in inputs:
    h = preserve(item['path'])
    objects.append({'blob': h, 'role': item['role'], 'selector': {'path_at_execution': item['path']}, 'source_identity': ''})
refs = []
for name in ['audit-execution-r001.json', 'audit-execution-r001.json.stderr',
             'audit-execution-r002.json', 'audit-execution-r003.json',
             'audit-execution-r003.json.stdout', 'audit-execution-r003.json.stderr', 'audit-validation.json']:
    refs.append(preserve(O / name, 'derived'))
producer = preserve(receipt['producer'], 'code')
base = {'kind': 'causal-evidence-audit', 'summary': 'Attributed source applicability and inherited eligibility verification; NRF2 necessity for PMP22 suppression is not identified. No new expression screen or wet-lab result.',
        'limitations': ['Agent-curated source assessments are not experimental observations.',
                        'Inherited results are reused, not independent replication.',
                        'No eligible matched Schwann Nae1-by-Nrf2 nascent-PMP22 design in retrieved evidence; search is not exhaustive.',
                        'Library labels do not establish donor independence; skin factorial is a different target compartment.',
                        'Failed and successful producer receipts retained; final output hashes correspond to r003.'],
        'derivation': {'inputs': objects, 'code': [producer], 'references': refs,
                       'command': receipt['argv'], 'environment': audit['environment'],
                       'parameters': {'question': 'q_90f4fed27b7e4793', 'producer_receipt_sha256': sha(O / 'audit-execution-r003.json'),
                                      'scope': 'source and metadata audit, eligibility verification, pre-experiment epistasis design'}}}
products = {
 'causal-evidence-audit.json': ('NRF2 necessity for PMP22: causal evidence and applicability audit', 'causal-audit'),
 'sample-assay-eligibility.tsv': ('Nae1 nerve and Nedd8 NRF2 skin sample eligibility', 'sample-assay-eligibility'),
 'locked-panel-eligibility.tsv': ('Original antioxidant panel: measured versus locked-floor eligibility', 'locked-panel-eligibility'),
 'epistasis-decision-table.tsv': ('PMP22 NRF2 factorial epistasis predictions', 'epistasis-decision-table'),
 'source-locators.tsv': ('Primary source locators and causal exclusions', 'source-locators')}
for name, (title, role) in products.items():
    manifest = dict(base, title=title, output_role=role)
    (R / (name + '.manifest.json')).write_text(json.dumps(manifest, indent=2, allow_nan=False))
print(json.dumps(validation, indent=2, allow_nan=False))
print('Prepared registration manifests: ' + ', '.join(products))
