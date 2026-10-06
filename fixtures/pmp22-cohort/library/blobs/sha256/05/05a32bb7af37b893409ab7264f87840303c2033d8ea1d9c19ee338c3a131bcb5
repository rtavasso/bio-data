"""Inspect native input identities and formats before selecting an analysis."""
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
import openpyxl

q = Path(__file__).resolve().parents[1]
def locate(h):
    r = subprocess.run(['./bin/bio', 'object', 'show', h], capture_output=True, text=True, check=True)
    return Path(json.loads(r.stdout)['path'])
manifest = json.loads((q / 'outputs/selectivity-manifest.json').read_text())
records = []
for inp in manifest['manifest']['derivation']['inputs']:
    h = inp['blob']
    p = locate(h)
    data = p.read_bytes()
    assert hashlib.sha256(data).hexdigest() == h
    if data[:2] == b'\x1f\x8b':
        with gzip.open(p, 'rt') as f:
            preview = ''.join(next(f, '') for _ in range(4))
    elif data[:2] == b'PK':
        preview = 'ZIP container'
    else:
        preview = data[:3500].decode('utf-8', errors='replace')
    record = {'blob': h, 'path': str(p), 'bytes': len(data), 'preview': preview}
    records.append(record)
    print(json.dumps(record))
(q / 'outputs/selectivity-input-inspection.json').write_text(json.dumps(records, indent=2) + '\n')
h = '3c1be01fc49ea6b7eb7b527352c032e8e9987e4db78ed2a0bcc79b53b902b5b6'
p = locate(h)
with p.open('rb') as f:
    wb = openpyxl.load_workbook(f, read_only=True, data_only=False)
    for ws in wb:
        print('FIGLIA', ws.title, ws.max_row, ws.max_column)
        for row in ws.iter_rows(min_row=1, max_row=5, values_only=True):
            print(repr(row))
