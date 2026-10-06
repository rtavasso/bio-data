"""Resolve exact inherited input blobs and inspect static representations only."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

Q = Path(__file__).resolve().parents[1]
obj = json.loads((Q / 'outputs/selective-gene-artifact-fetched.json').read_text())
records = []
for item in obj['manifest']['derivation']['inputs']:
    h = item['blob']
    p = subprocess.run(['./bin/bio', 'object', 'show', h], capture_output=True, text=True, check=True)
    loc = json.loads(p.stdout)
    path = Path(loc['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == h
    prefix = path.read_bytes()[:300]
    if prefix.startswith(b'\x1f\x8b'):
        with gzip.open(path, 'rt') as stream:
            prefix = stream.readline().encode()[:300]
    print(h, path.stat().st_size, repr(prefix))
    records.append({'blob': h, 'path': str(path), 'bytes': path.stat().st_size, 'prefix': prefix.decode(errors='replace')})
(Q / 'outputs/peer-input-inventory.json').write_text(json.dumps(records, indent=2))
