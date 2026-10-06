"""Read back the exact published evidence and verify shared bytes, without reanalysis."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

q = Path(__file__).resolve().parents[1]
root = q.parents[2]
out = q / 'outputs'
shared = Path(os.environ['BIO_COMMUNITY']) / 'library'


def call(args):
    p = subprocess.run([str(root / 'bin/bio'), *args], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_shared(h):
    data = (shared / 'blobs/sha256' / h[:2] / h).read_bytes()
    assert sha(data) == h
    return data


pid = json.loads((out / 'publication-receipt.json').read_text())['id']
post = call(['community', 'show', pid])
assert post['id'] == pid and post['author'] == 'agent_9daa318e4d8b42d8827c49a7a8b750e2'
assert post['content']['body'] == (out / 'PUBLICATION.md').read_text()
(out / 'publication-readback.json').write_text(json.dumps(post, indent=2, allow_nan=False))
expected = {}
for p in sorted((q / 'inputs').glob('artifact_*.stdout.json')):
    d = json.loads(p.read_text())
    expected[d['id']] = d
for name in ['stress-source-evidence.zip', 'source-locator-manifest.json', 'sample-locators.json', 'byte-verification.json']:
    d = json.loads((out / 'registrations' / (name + '.readback.json')).read_text())
    expected[d['id']] = d
assert len(expected) == 9 and set(post['content']['evidence']['artifacts']) == set(expected)
results = []
archive_members = None
for aid, local in expected.items():
    public = call(['--workspace', str(shared), 'artifact', 'show', aid])
    assert public['manifest'] == local['manifest']
    assert public['output_blob'] == local['output_blob']
    data = read_shared(public['output_blob'])
    for item in public['manifest']['derivation']['inputs']:
        read_shared(item['blob'])
    for h in public['manifest']['derivation']['code']:
        read_shared(h)
    if public['manifest']['output']['name'] == 'stress-source-evidence.zip':
        assert data == (out / 'stress-source-evidence.zip').read_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest_data = archive.read('source-locator-manifest.json')
            assert manifest_data == (out / 'source-locator-manifest.json').read_bytes()
            manifest = json.loads(manifest_data)
            assert set(archive.namelist()) == {x['member'] for x in manifest['files']} | {'source-locator-manifest.json'}
            for item in manifest['files']:
                payload = archive.read(item['member'])
                assert sha(payload) == item['sha256'] and len(payload) == item['bytes']
            archive_members = len(archive.namelist())
    results.append(dict(artifact=aid, output_sha256=public['output_blob'], original_manifest_identity=True,
                        shared_input_code_output_verified=True))
assert archive_members == json.loads((out / 'byte-verification.json').read_text())['archive_members']
result = dict(valid=True, post=pid, exact_post_body=True, published_artifacts=len(results),
              archive_members_verified=archive_members, artifacts=results, scientific_rerun=False)
(out / 'publication-verification.json').write_text(json.dumps(result, indent=2, allow_nan=False))
print(json.dumps(result, indent=2))
