"""Inspect published state-audit products without recomputing biological results."""
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parents[1] / 'outputs'
post = json.loads((out / 'state-notification-publication.json').read_text())
print('Publication', post['id'], 'superseded_by', post['superseded_by'], 'replies', post['replies'])
for stem in ['state-paired', 'state-applicability']:
    a = json.loads((out / (stem + '-review-manifest.json')).read_text())
    p = Path(a['path'])
    assert p.stat().st_size < 150_000
    data = p.read_bytes()
    assert hashlib.sha256(data).hexdigest() == a['output_blob']
    dest = out / (stem + '-reviewed' + Path(a['manifest']['output']['name']).suffix)
    dest.write_bytes(data)
    print(a['id'], len(data), 'bytes;', dest, '; hash verified')
