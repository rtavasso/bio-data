"""Preserve selected source and annotation bytes in the local object store."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

Q = Path(__file__).resolve().parents[1]
ROOT = Q.parents[2]
WS = Path(os.environ['BIO_WORKSPACE']).resolve()
source = WS / 'blobs/sha256/06/06dbbac706e6f32b1f8320b277da99493ef0f0a061058911a8307000f1d47b56'
dest = Q / 'reused/PMC7145652.xml'
dest.parent.mkdir(exist_ok=True)
assert hashlib.sha256(source.read_bytes()).hexdigest() == source.name
if dest.exists():
    assert dest.read_bytes() == source.read_bytes()
else:
    shutil.copyfile(source, dest)
annotations = json.loads((Q / 'inputs/evidence-annotations.json').read_text())
paths = {Q / path for context in annotations['contexts'] for path in context['files']}
paths |= {Q / 'inputs/analysis-plan.json', Q / 'inputs/evidence-annotations.json',
          Q / 'inputs/native/extraction-manifest.json'}
paths |= set((Q / 'inputs/public').glob('*.receipt.json'))
paths |= set((Q / 'inputs/community').glob('*.json'))
records = []
for path in sorted(paths):
    result = subprocess.run(['./bin/bio', 'object', 'add', str(path)], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    obj = json.loads(result.stdout)
    blob = obj['blob']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == blob
    assert Path(obj['path']).read_bytes() == path.read_bytes()
    records.append({'relative_path': str(path.relative_to(Q)), 'blob': blob,
                    'object_path': obj['path'], 'bytes': obj['bytes']})
out = Q / 'inputs/immutable-inputs.json'
with out.open('x') as f:
    json.dump({'question': Q.name, 'inputs': records}, f, indent=2, allow_nan=False)
    f.write('\n')
print(json.dumps({'staged_count': len(records), 'manifest': str(out)}, indent=2))
