"""Finish separate-role registrations and verify exact catalog targets."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_90f4fed27b7e4793'
r = q / 'outputs/registration'
first = json.loads((r / 'causal-evidence-audit.json.receipt.json').read_text())
assert first['artifact'].startswith('artifact_') and not first['conflicting_outputs']
products = ['causal-evidence-audit.json', 'sample-assay-eligibility.tsv',
            'locked-panel-eligibility.tsv', 'epistasis-decision-table.tsv', 'source-locators.tsv']
index = []
for name in products:
    receipt_path = r / (name + '.receipt.json')
    if not receipt_path.exists():
        result = subprocess.run(['./bin/bio', 'register', str(q / 'outputs' / name),
                                 '--manifest', str(r / (name + '.manifest.json')),
                                 '--question', 'q_90f4fed27b7e4793'], capture_output=True, text=True, check=True)
        receipt_path.write_text(result.stdout)
    receipt = json.loads(receipt_path.read_text())
    assert not receipt['conflicting_outputs'], receipt
    result = subprocess.run(['./bin/bio', 'artifact', 'show', receipt['artifact']],
                            capture_output=True, text=True, check=True)
    (r / (name + '.verified.json')).write_text(result.stdout)
    info = json.loads(result.stdout)
    h = hashlib.sha256((q / 'outputs' / name).read_bytes()).hexdigest()
    assert info['output_blob'] == receipt['output_blob'] == h
    assert any(i['question_id'] == 'q_90f4fed27b7e4793' for i in info['questions'])
    index.append({'file': name, 'artifact': receipt['artifact'], 'output_blob': h,
                  'output_role': info['output_role'], 'verified': True})
(q / 'outputs/artifact-index.json').write_text(json.dumps(index, indent=2, allow_nan=False))
print(json.dumps(index, indent=2, allow_nan=False))
