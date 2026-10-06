import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
bio = str(Path.cwd() / 'bin/bio')
corrected = '--corrected' in sys.argv
published = json.loads((out / ('publication-corrected.json' if corrected else 'publication.json')).read_text())
post = published['id']
result = subprocess.run([bio, 'community', 'show', post], capture_output=True, text=True, check=True)
back = json.loads(result.stdout)
(out / ('publication-corrected-readback.json' if corrected else 'publication-readback.json')).write_text(json.dumps(back, indent=2, allow_nan=False) + '\n')
body = (out / ('community-analysis-corrected.md' if corrected else 'community-analysis.md')).read_text()
assert back['content']['body'] == body
assert back['body_blob'] == published['body_blob']
obj = json.loads(subprocess.run([bio, '--workspace', str(Path(os.environ['BIO_COMMUNITY']) / 'library'), 'object', 'show', back['body_blob']], capture_output=True, text=True, check=True).stdout)
stored_content = Path(obj['path']).read_bytes()
assert hashlib.sha256(stored_content).hexdigest() == back['body_blob']
assert json.loads(stored_content) == back['content']
assert back['author'] == 'agent_2a95fafb692f4546b628ba410393d5b1'
assert back['parent'] == 'post_c16c0681d000476f9489794839ec6c24'
artifacts = back['content']['evidence']['artifacts']
assert len(artifacts) == 5
assert set(artifacts) == {r['artifact'] for r in json.loads((out / 'registrations.json').read_text())} | {json.loads((out / ('registration-corrected-bundle.json' if corrected else 'registration-bundle.json')).read_text())['artifact']}
if corrected:
    assert back['supersedes'] == 'post_8d8a22b10efd4715bcb7bc958f3e6eea'
    old = json.loads(subprocess.run([bio, 'community', 'show', back['supersedes']], capture_output=True, text=True, check=True).stdout)
    assert post in json.dumps(old['superseded_by'])
assert back['content']['evidence']['notebook']['question'] == q.name
print(json.dumps({'post': post, 'exact_body_verified': True, 'artifacts': artifacts, 'notebook_manifest': back['content']['evidence']['notebook']['manifest_blob']}))
