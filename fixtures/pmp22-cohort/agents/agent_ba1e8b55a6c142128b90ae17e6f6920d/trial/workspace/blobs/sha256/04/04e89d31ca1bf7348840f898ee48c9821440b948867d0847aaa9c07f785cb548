"""Read back exact publication, shared output bytes and completed question status."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'


def cli(args):
    result = subprocess.run(['./bin/bio', *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


receipt = json.loads((OUT / 'publication-receipt.json').read_text())
post = cli(['community', 'show', receipt['id']])
(OUT / 'publication-readback.json').write_text(json.dumps(post, indent=2))
assert post['content']['body'].strip() == (OUT / 'publication.md').read_text().strip()
expected = []
for role in ['endpoint-audit', 'assay-eligibility', 'source-locators', 'bidirectionality-design', 'audit-validation']:
    reg = json.loads((OUT / 'registration' / f'{role}.json').read_text())
    expected.append(reg['artifact'])
    obj = cli(['--workspace', str(Path(os.environ['BIO_COMMUNITY']) / 'library'),
               'object', 'show', reg['output_blob']])
    assert obj['blob'] == reg['output_blob']
    assert hashlib.sha256(Path(obj['path']).read_bytes()).hexdigest() == reg['output_blob']
assert sorted(post['content']['evidence']['artifacts']) == sorted(expected)
question = cli(['work', 'show', 'q_d14c6e25fa864ab5'])
assert question['status'] == 'completed'
for direction in [[], ['--sent']]:
    inbox = cli(['community', 'inbox', *direction])
    name = 'inbox-sent-final.json' if direction else 'inbox-final.json'
    (OUT / name).write_text(json.dumps(inbox, indent=2))
summary = {'post': post['id'], 'publication_exact_body_verified': True,
           'shared_artifacts_verified': len(expected), 'question_status': question['status']}
(OUT / 'publication-verification.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary))
