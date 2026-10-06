"""Read back this publication and verify immutable shared bytes; no scientific rerun."""
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
for name in ['original-lipid-artifact.json', 'original-lipid-table-artifact.json']:
    d = json.loads((q / 'inputs' / name).read_text())
    expected[d['id']] = d
for name in ['lipid-source-evidence.zip', 'source-locator-manifest.json', 'byte-verification.json', 'ADVS-13-e20323-s002.docx']:
    d = json.loads((out / 'registrations' / (name + '.readback.json')).read_text())
    expected[d['id']] = d
assert len(expected) == 6 and set(post['content']['evidence']['artifacts']) == set(expected)
inspection = json.loads((out / 'archive-inspection.json').read_text())
forbidden_core_inputs = {inspection[k] for k in ['outer_sha256', 'nested_sha256', 'docx_sha256']}
results = []
archive_members = None
for aid, local in expected.items():
    public = call(['--workspace', str(shared), 'artifact', 'show', aid])
    assert public['manifest'] == local['manifest']
    assert public['output_blob'] == local['output_blob']
    data = read_shared(public['output_blob'])
    inputs = public['manifest']['derivation']['inputs']
    for item in inputs:
        read_shared(item['blob'])
    for h in public['manifest']['derivation']['code']:
        read_shared(h)
    name = public['manifest']['output']['name']
    if (out / name).is_file():
        assert data == (out / name).read_bytes()
    if name == 'lipid-source-evidence.zip':
        assert not forbidden_core_inputs.intersection({i['blob'] for i in inputs})
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest_data = archive.read('source-locator-manifest.json')
            assert manifest_data == (out / 'source-locator-manifest.json').read_bytes()
            manifest = json.loads(manifest_data)
            assert set(archive.namelist()) == {x['member'] for x in manifest['files']} | {'source-locator-manifest.json'}
            for item in manifest['files']:
                payload = archive.read(item['member'])
                assert sha(payload) == item['sha256'] and len(payload) == item['bytes']
            archive_members = len(archive.namelist())
    if name == 'ADVS-13-e20323-s002.docx':
        assert sha(data) == inspection['docx_sha256'] and len(data) == inspection['docx_bytes']
    results.append(dict(artifact=aid, output_sha256=public['output_blob'], original_manifest_identity=True,
                        shared_input_code_output_verified=True))
assert archive_members == json.loads((out / 'byte-verification.json').read_text())['archive_members']
result = dict(valid=True, post=pid, exact_post_body=True, published_artifacts=len(results),
              archive_members_verified=archive_members, artifacts=results,
              native_docx_verified=True, large_payloads_excluded_from_core=True,
              PMC6623163_full_text_provided=False, scientific_rerun=False)
(out / 'publication-verification.json').write_text(json.dumps(result, indent=2, allow_nan=False))
print(json.dumps(result, indent=2))
