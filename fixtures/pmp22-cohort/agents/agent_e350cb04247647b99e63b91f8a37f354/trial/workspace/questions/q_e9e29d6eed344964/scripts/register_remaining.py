"""Register the remaining distinct products and verify every catalog readback."""
import hashlib
import json
from pathlib import Path
import subprocess

P = Path(__file__).resolve().parents[1]
OUT = P / 'outputs'
products = ['evidence-package.json', 'cis-evidence.tsv', 'rat-promoter-map.tsv',
            'pmp22-tss-clusters.tsv', 'sample-eligibility.tsv']
verified = []
for name in products:
    receipt_path = OUT / ('registration-main.json' if name == products[0] else 'registration-' + name + '.json')
    if not receipt_path.exists():
        result = subprocess.run(['./bin/bio', 'register', str(OUT / name), '--manifest',
                                 str(OUT / (name + '.manifest.json')), '--question', 'q_e9e29d6eed344964'],
                                capture_output=True, text=True, check=True)
        receipt_path.write_text(result.stdout)
    receipt = json.loads(receipt_path.read_text())
    assert not receipt['conflicting_outputs'] and receipt['warning'] is None
    assert receipt['output_blob'] == hashlib.sha256((OUT / name).read_bytes()).hexdigest()
    result = subprocess.run(['./bin/bio', 'artifact', 'show', receipt['artifact']],
                            capture_output=True, text=True, check=True)
    (OUT / ('readback-' + name + '.json')).write_text(result.stdout)
    info = json.loads(result.stdout)
    assert info['output_blob'] == receipt['output_blob']
    verified.append({'file': name, 'artifact': receipt['artifact'], 'output_blob': receipt['output_blob']})
(OUT / 'registered-products.json').write_text(json.dumps(verified, indent=2) + '\n')
print(json.dumps(verified, indent=2))
