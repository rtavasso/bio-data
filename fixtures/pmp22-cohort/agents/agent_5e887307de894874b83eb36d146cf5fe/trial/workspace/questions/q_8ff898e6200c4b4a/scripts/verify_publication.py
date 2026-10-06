"""Read back exact publication and shared artifacts, then recheck unlaunched boundary."""
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs'
R = OUT / 'receipts'


def cli(*args):
    return json.loads(subprocess.check_output(['./bin/bio', *args], text=True))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


receipt = json.loads((R / 'setup-evidence-publish.json').read_text())
actual = cli('community', 'show', receipt['id'])
save(R / 'setup-evidence-readback.json', actual)
assert actual['author'] == os.environ['BIO_AGENT'] == 'agent_5e887307de894874b83eb36d146cf5fe'
assert actual['parent'] == 'post_569bb436329e46828ed286a26425ab03'
assert actual['content']['body'] == (OUT / 'setup-publication.md').read_text()
assert actual['request_key'] == 'pmp22-cohort-q_8ff898e6200c4b4a-setup-evidence'
products = json.loads((OUT / 'registered-outputs.json').read_text())
assert set(actual['content']['evidence']['artifacts']) == {p['artifact'] for p in products}
lib = str(Path(os.environ['BIO_COMMUNITY']) / 'library')
for product in products:
    shared = cli('--workspace', lib, 'artifact', 'show', product['artifact'])
    save(R / (product['role'] + '.shared-readback.json'), shared)
    assert shared['id'] == product['artifact'] and shared['output_blob'] == product['output_blob']
    assert hashlib.sha256(Path(shared['path']).read_bytes()).hexdigest() == product['output_blob']
manifest_blob = actual['content']['evidence']['notebook']['manifest_blob']
manifest_path = cli('--workspace', lib, 'object', 'show', manifest_blob)['path']
manifest = json.loads(Path(manifest_path).read_text())
assert manifest['question'] == Q.name and manifest['status'] == 'completed'
assert manifest['files']['LABBOOK.md'] == hashlib.sha256((Q / 'LABBOOK.md').read_bytes()).hexdigest()
save(R / 'published-final-notebook-manifest.json', manifest)
cohort = json.loads((OUT / 'cohort.json').read_text())
ids = {a['id'] for a in cohort['agents']}
audit = cli('community', 'audit')
save(R / 'post-publication-board-audit.json', audit)
members = [a for a in audit['agents'] if a['id'] in ids]
requests = [r for r in audit['requests'] if r['target'] in ids]
attempts = [a for a in audit['attempts'] if a['target'] in ids]
assert len(members) == len(ids) == 10 and all(a['native_session'] is None for a in members)
assert not attempts and len(requests) == 10
assert all(len([r for r in requests if r['target'] == aid]) == 1 for aid in ids)
assert all(r['state'] == 'pending' and r['active_run'] is None and r['answer'] is None for r in requests)
# Validate hand-written publication request table against the generated, already verified cohort.
body = actual['content']['body']
for agent in cohort['agents']:
    assert '| ' + agent['name'] + ' | ' + agent['request_id'] + ' | ' + agent['question_post'] + ' |' in body
result = {'verified_at': datetime.now(UTC).isoformat(), 'post': actual['id'], 'author': actual['author'],
          'parent': actual['parent'], 'shared_artifacts_verified': products, 'notebook_manifest': manifest_blob,
          'exact_body_verified': True, 'members': len(members), 'pending': len(requests),
          'attempts': len(attempts), 'all_native_sessions_null': True}
save(OUT / 'publication-verification.json', result)
print(json.dumps(result, indent=2))
