"""Read back the handoff addendum and registered bytes, without new analysis."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs/handoff-r001'


def cli(args):
    p = subprocess.run(['./bin/bio', *args], text=True, capture_output=True, check=True)
    return json.loads(p.stdout)


receipt = json.loads((OUT / 'publication-receipt.json').read_text())
post = cli(['community', 'show', receipt['id']])
(OUT / 'publication-readback.json').write_text(json.dumps(post, indent=2))
assert post['content']['body'] == (OUT / 'addendum.md').read_text()
expected = []
for name in ['locator-artifact.json', 'bundle-artifact.json', 'artifact-readback.json']:
    meta = json.loads((OUT / name).read_text())
    expected.append(meta['id'])
    obj = cli(['--workspace', str(Path(os.environ['BIO_COMMUNITY']) / 'library'), 'object', 'show', meta['output_blob']])
    assert hashlib.sha256(Path(obj['path']).read_bytes()).hexdigest() == meta['output_blob']
reg = json.loads((OUT / 'registration.json').read_text())
assert hashlib.sha256((OUT / 'handoff-verification.json').read_bytes()).hexdigest() == reg['output_blob']
assert sorted(expected) == sorted(post['content']['evidence']['artifacts'])
question = cli(['work', 'show', 'q_d14c6e25fa864ab5'])
(OUT / 'question-readback.json').write_text(json.dumps(question, indent=2))
assert question['status'] == 'completed'
summary = {'post': post['id'], 'body_exact': True, 'shared_artifacts_verified': len(expected),
           'question_status': question['status'], 'biological_reanalysis': False}
(OUT / 'publication-verification.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary))
for name in ['inbox-final.json', 'inbox-sent-final.json']:
    print(name, json.dumps(json.loads((OUT / name).read_text()), indent=2))
