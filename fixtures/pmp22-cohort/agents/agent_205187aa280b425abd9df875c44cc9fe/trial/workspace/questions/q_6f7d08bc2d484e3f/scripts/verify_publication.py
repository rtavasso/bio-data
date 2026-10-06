"""Read back the exact publication, notebook status and shared artifact bytes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

Q = Path(__file__).resolve().parents[1]
ROOT = Q.parents[2]


def bio(*args):
    r = subprocess.run(['./bin/bio', *map(str, args)], cwd=ROOT,
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


publication = json.loads((Q / 'inputs/community/publication-receipt.json').read_text())
readback = bio('community', 'show', publication['id'])
assert readback['id'] == publication['id']
assert readback['author'] == 'agent_205187aa280b425abd9df875c44cc9fe'
assert readback['content']['body'] == (Q / 'outputs/publication.md').read_text()
assert readback['content']['evidence'] == publication['content']['evidence']
assert readback['parent'] == 'post_d5bdaf468e0a4a85a1381ee478754d30'
with (Q / 'inputs/community/publication-readback.json').open('x') as f:
    json.dump(readback, f, indent=2, allow_nan=False)
work = bio('work', 'show', Q.name)
assert work['status'] == 'completed'
notebook_blob = work['snapshot']['files']['LABBOOK.md']
assert hashlib.sha256((Q / 'LABBOOK.md').read_bytes()).hexdigest() == notebook_blob
library = Path(os.environ['BIO_COMMUNITY']) / 'library'
checks = []
for aid in readback['content']['evidence']['artifacts']:
    local = bio('artifact', 'show', aid)
    shared = bio('--workspace', library, 'artifact', 'show', aid)
    assert shared['output_blob'] == local['output_blob']
    assert hashlib.sha256(Path(shared['path']).read_bytes()).hexdigest() == shared['output_blob']
    assert Path(shared['path']).read_bytes() == Path(local['path']).read_bytes()
    checks.append({'artifact': aid, 'blob': shared['output_blob'], 'shared_bytes_verified': True})
obj = bio('--workspace', library, 'object', 'show', notebook_blob)
assert Path(obj['path']).read_bytes() == (Q / 'LABBOOK.md').read_bytes()
result = {'status': 'passed', 'post': readback['id'], 'question_status': work['status'],
          'published_body_equal': True, 'notebook_blob': notebook_blob,
          'shared_notebook_equal': True, 'artifacts': checks}
with (Q / 'outputs/publication-validation.json').open('x') as f:
    json.dump(result, f, indent=2, allow_nan=False)
    f.write('\n')
print(json.dumps(result, indent=2))
