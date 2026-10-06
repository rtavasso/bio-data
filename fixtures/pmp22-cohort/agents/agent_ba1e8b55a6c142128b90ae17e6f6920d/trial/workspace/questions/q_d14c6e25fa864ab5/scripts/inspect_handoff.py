"""Read-only checks of newly shared static evidence; never execute inherited code."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs/handoff-r001'
for name in ['locator', 'bundle']:
    meta = json.loads((OUT / f'{name}-artifact.json').read_text())
    p = Path(meta['path'])
    assert hashlib.sha256(p.read_bytes()).hexdigest() == meta['output_blob']
    print(name, meta['id'], meta['output_blob'], p.stat().st_size)
    if name == 'locator':
        obj = json.loads(p.read_text())
        (OUT / 'locator-readable.json').write_text(json.dumps(obj, indent=2))
        print(json.dumps(obj, indent=2))
    else:
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None
            print('MEMBERS', json.dumps(z.namelist(), indent=2))
for name in ['forum-abca1.json', 'forum-fdft1.json']:
    doc = json.loads((OUT / name).read_text())
    print(name, 'total', doc['total'], 'next_offset', doc['next_offset'])
    for item in doc['items']:
        print(item['subject'], item['title'], item.get('superseded_by'))
if len(sys.argv) > 1:
    raise ValueError('No imported code execution mode is supported')
