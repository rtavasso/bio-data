"""Read back the exact forum post and published artifact bytes from the shared library."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
import io

q = Path(__file__).resolve().parents[1]
root = q.parents[2]
w = root / 'workspace'
shared = Path(os.environ['BIO_COMMUNITY']) / 'library'
out = q / 'outputs'


def call(args):
    result = subprocess.run([str(root / 'bin/bio'), *args], capture_output=True,
                            text=True, check=True)
    return json.loads(result.stdout)


def sha(data):
    return hashlib.sha256(data).hexdigest()


receipt = json.loads((out / 'publication-receipt.json').read_text())
pid = receipt['id']
post = call(['community', 'show', pid])
assert post['id'] == pid and post['author'] == 'agent_9daa318e4d8b42d8827c49a7a8b750e2'
assert post['content']['body'] == (out / 'PUBLICATION.md').read_text()
(out / 'publication-readback.json').write_text(json.dumps(post, indent=2, allow_nan=False))
expected = [(json.loads((out / 'registrations' / (name + '.json')).read_text())['artifact'], name)
            for name in ('protein-evidence.zip', 'share-manifest.json', 'byte-verification.json')]
expected.append(('artifact_c30116363838ac218b965a4b0e5ccc5420e5df8f0b6bb4f9d7b47ba00a96ca4a', None))
results = []
for aid, name in expected:
    local = call(['artifact', 'show', aid])
    public = call(['--workspace', str(shared), 'artifact', 'show', aid])
    assert public['output_blob'] == local['output_blob']
    h = public['output_blob']
    data = (shared / 'blobs/sha256' / h[:2] / h).read_bytes()
    assert sha(data) == h
    if name:
        assert data == (out / name).read_bytes()
    else:
        assert data == (w / 'questions/q_277f20df4b6b47cc/outputs/protein-analysis-summary.json').read_bytes()
    for item in public['manifest']['derivation']['inputs']:
        h2 = item['blob']
        assert sha((shared / 'blobs/sha256' / h2[:2] / h2).read_bytes()) == h2
    for h2 in public['manifest']['derivation']['code']:
        assert sha((shared / 'blobs/sha256' / h2[:2] / h2).read_bytes()) == h2
    if name == 'protein-evidence.zip':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read('share-manifest.json'))
            for item in manifest['files']:
                payload = archive.read(item['member'])
                assert len(payload) == item['bytes'] and sha(payload) == item['sha256']
    results.append({'artifact': aid, 'output_sha256': h, 'shared_inputs_and_code_present': True})
verification = {'valid': True, 'post': pid, 'post_body_matches': True, 'shared_artifacts': results}
(out / 'publication-verification.json').write_text(json.dumps(verification, indent=2, allow_nan=False))
print(json.dumps(verification, indent=2))
