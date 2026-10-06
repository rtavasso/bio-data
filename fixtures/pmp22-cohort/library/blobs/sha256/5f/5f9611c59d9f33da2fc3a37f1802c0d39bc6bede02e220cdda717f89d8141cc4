"""Read selected immutable JSON evidence, never execute inherited code."""
import json
import os
from pathlib import Path

q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_ec00fef1019a4c6f'
lib = Path(os.environ['BIO_COMMUNITY']) / 'library/blobs/sha256'
def blob(h):
    return lib / h[:2] / h
manifest = json.loads(blob('e054cae33492c105e41221766e86dc067d7c5dfeaf75fc8409c23b468964166b').read_text())
(q / 'outputs/prior-notebook-manifest.pretty.json').write_text(json.dumps(manifest, indent=2))
for name in ['state', 'composition']:
    obj = json.loads((q / f'outputs/{name}-manifest.json').read_text())
    (q / f'outputs/{name}-manifest.pretty.json').write_text(json.dumps(obj, indent=2))
    print(name, json.dumps({k: v for k, v in obj.items() if k != 'manifest'}, indent=2))
    print('MANIFEST KEYS', list(obj['manifest']))
    print('OUTPUT', obj['manifest'].get('output'))
print('NOTEBOOK FILES', json.dumps(manifest.get('files'), indent=2))
