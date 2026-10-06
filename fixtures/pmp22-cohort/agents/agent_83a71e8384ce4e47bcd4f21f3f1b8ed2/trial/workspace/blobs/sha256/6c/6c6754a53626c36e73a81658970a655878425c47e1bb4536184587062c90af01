"""Read immutable saved sources; inspect data eligibility before target analysis."""

import gzip
import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET
q = Path(__file__).resolve().parents[1]
w = Path(os.environ['BIO_WORKSPACE'])
h = '78eeaf73be9d1576d1713c3a97b9988d386f713a21842f128eeb3f0a45f7d295'
p = w / 'blobs/sha256' / h[:2] / h
with gzip.open(p, 'rt') as f:
    for i, line in enumerate(f):
        if i < 5 or 'PMP22' in line:
            print('native line', i + 1, line.rstrip())
print('COUNT LINES', i + 1)
for name in ['PMC13431160', 'PMC9852534', 'PMC3002990']:
    root = ET.parse(q / 'inputs/primary' / (name + '.source')).getroot()
    print(name, ''.join(root.find('.//article-title').itertext()))
    for e in root.iter('p'):
        text = ' '.join(''.join(e.itertext()).split())
        keys = ['s4U', '4sU', 'SLAMseq', 'IRE1 activity'] if name == 'PMC13431160' else ['PMP22', 'Pmp22', 'miR-29', 'miR-17', 'RIDD']
        if any(k in text for k in keys):
            print(text)
for file in ['bundle_34c53097b66a18c0797661f1.json', 'bundle_14000f9ebab7cc60dec474f4.json']:
    obj = json.loads((q / 'inputs/geo' / file).read_text())
    for r in obj['relationships']:
        if not r['locator'].startswith('GSM'):
            print('SERIES RELATION', r)
