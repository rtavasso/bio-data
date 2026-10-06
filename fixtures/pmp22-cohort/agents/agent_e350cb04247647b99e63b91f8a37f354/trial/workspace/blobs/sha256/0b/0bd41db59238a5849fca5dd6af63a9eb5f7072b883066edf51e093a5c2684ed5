"""Preserve selected native input bytes and their actual transport receipts."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'sources'
selected = [
    'GSE139321-metadata.json',
    'primary/12864_2020_6963_MOESM2_ESM.xlsx',
    'primary/PMC7430845-supplements.zip',
    'primary/PMC7430845.xml',
    'primary/PMC6482019.xml',
    'primary/PMC7145652.xml',
    'primary/PMC3100536-bioc.xml',
    'primary/PMC10959528.xml',
    'primary/rn5-refGene-Pmp22.json',
    'primary/NM_017037.gb',
    'primary/PMC3298281-meta.json',
    'primary/PMC6077802-meta.json',
    'primary/PMC7322568-meta.json',
    'primary/PMC5181599-meta.json',
    'primary/pmp22-cis-nascent-search.json',
    'primary/schwann-tss-assays-search.json',
    'primary/schwann-cis-perturbation-search.json',
    'mechanism_map.json',
    'primary/Pantera-thesis.pdf',
    'primary/Pantera-thesis.txt',
    'primary/rn5-Pmp22-promoter-sequence.json',
    'curated-evidence.json',
    'transport-receipts.json',
]
transport = []
for path in sorted((SOURCES / 'primary').glob('*.receipt.json')):
    raw = path.read_bytes()
    transport.append({'relative_path': str(path.relative_to(SOURCES)),
                      'sha256': hashlib.sha256(raw).hexdigest(),
                      'original_text': raw.decode('utf-8')})
(SOURCES / 'transport-receipts.json').write_text(json.dumps(transport, indent=2) + '\n')
records = {}
for name in selected:
    path = SOURCES / name
    result = subprocess.run(['./bin/bio', 'object', 'add', str(path)], capture_output=True, text=True, check=True)
    receipt = json.loads(result.stdout)
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt['blob'] == h
    records[name] = receipt
(SOURCES / 'immutable-inputs.json').write_text(json.dumps(records, indent=2) + '\n')
print(json.dumps({'native_inputs_preserved': len(records), 'manifest': str(SOURCES / 'immutable-inputs.json')}))
