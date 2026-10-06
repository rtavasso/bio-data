"""Verify the exact published post, shared artifact bytes and archive members."""
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
    result = subprocess.run([str(root / 'bin/bio'), *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def sha(data):
    return hashlib.sha256(data).hexdigest()


receipt = json.loads((out / 'publication-receipt.json').read_text())
pid = receipt['id']
post = call(['community', 'show', pid])
assert post['id'] == pid and post['author'] == 'agent_9daa318e4d8b42d8827c49a7a8b750e2'
assert post['content']['body'] == (out / 'PUBLICATION.md').read_text()
(out / 'publication-readback.json').write_text(json.dumps(post, indent=2, allow_nan=False))
results = []
for name in ('cis-source-evidence.zip', 'source-locator-manifest.json',
             'GSE139321_Schwann_Cell_Tn5Prime_GEO_Processed.txt', 'byte-verification.json'):
    registration = json.loads((out / 'registrations' / (name + '.json')).read_text())
    aid = registration['artifact']
    public = call(['--workspace', str(shared), 'artifact', 'show', aid])
    h = public['output_blob']
    data = (shared / 'blobs/sha256' / h[:2] / h).read_bytes()
    assert sha(data) == h == registration['output_blob']
    assert data == (out / name).read_bytes()
    for item in public['manifest']['derivation']['inputs']:
        h2 = item['blob']
        assert sha((shared / 'blobs/sha256' / h2[:2] / h2).read_bytes()) == h2
    for h2 in public['manifest']['derivation']['code']:
        assert sha((shared / 'blobs/sha256' / h2[:2] / h2).read_bytes()) == h2
    if name == 'cis-source-evidence.zip':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read('source-locator-manifest.json'))
            for item in manifest['files']:
                payload = archive.read(item['member'])
                assert sha(payload) == item['sha256'] and len(payload) == item['bytes']
    results.append({'artifact': aid, 'output_sha256': h, 'shared_input_code_output_verified': True})
gaps = json.loads((out / 'gap-withdrawal-readback.json').read_text())
assert any(item['event'] == 'event_97465bb7ee754ddc99d013770944ad34' for item in gaps['withdrawn_events'])
result = {'valid': True, 'post': pid, 'post_body_matches': True,
          'shared_artifacts': results, 'mixed_gap_withdrawal_readback_verified': True}
(out / 'publication-verification.json').write_text(json.dumps(result, indent=2, allow_nan=False))
print(json.dumps(result, indent=2))
