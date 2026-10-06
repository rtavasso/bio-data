"""Verify and inspect existing evidence only; do not rerun QTL or end screens."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

q = Path(__file__).resolve().parents[1]
o = q / 'outputs'
saved = o / 'variants-coordination'
saved.mkdir(exist_ok=True)
registrations = json.loads((o / 'registrations-final.json').read_text())
verified = []
for name in ['end-site-map.tsv', 'transcript-site-map.tsv',
             'flair-PMP22-native-final.gtf', 'regulatory-site-map.tsv']:
    digest = hashlib.sha256((o / name).read_bytes()).hexdigest()
    assert digest == registrations[name]['output_blob']
    verified.append({'file': name, 'sha256': digest,
                     'artifact': registrations[name]['artifact']})
blob = '6783452eb108d94acc1630f366bc85e5d40803b8ee8655dfb63c034fff03f2da'
source = Path(os.environ['BIO_COMMUNITY']) / 'library/blobs/sha256' / blob[:2] / blob
raw = source.read_bytes()
assert hashlib.sha256(raw).hexdigest() == blob
record = json.loads(raw)
selected = []
for key, value in record.items():
    if isinstance(value, list):
        for row in value:
            if isinstance(row, dict) and row.get('tissue') == 'Adipose_Subcutaneous' and row.get('assay') == 'sqtl':
                selected.append({'source_key': key, 'row': row})
assert len(selected) == 1
(saved / 'peer-adipose-splice-row.json').write_text(json.dumps({
    'status': 'inspection_of_peer_output_not_independent_QTL_reanalysis',
    'artifact': 'artifact_378dd1dde1005fd0e0d90e022df9e66367227636b3f092afd63a1abd31f6624a',
    'verified_output_sha256': blob, 'selected': selected,
}, indent=2, allow_nan=False))
for label, args in [
    ('peer-interim', ['show', 'post_1a40eea3ef1c44758d2d67057c3cd5d4']),
    ('existing-handoff', ['show', 'post_cc57de79f888413a830efc53cb14f37d']),
    ('inbox', ['inbox']), ('sent', ['inbox', '--sent']),
]:
    p = subprocess.run(['./bin/bio', 'community', *args], capture_output=True,
                       text=True, check=True)
    data = json.loads(p.stdout)
    (saved / f'{label}.json').write_text(json.dumps(data, indent=2, allow_nan=False))
    if label == 'existing-handoff':
        assert data['content']['body'] == (q / 'ANSWER-VARIANTS.md').read_text()
        assert data['parent'] == 'post_ea5d050a7fbe4f0f9329f45d9f10c140'
        assert not data['superseded_by']
(saved / 'verification.json').write_text(json.dumps({
    'verified_local_outputs': verified, 'existing_handoff_exact': True,
    'peer_output_hash_verified': blob,
    'scope': 'evidence inspection; no new sequencing/QTL/end calculation',
}, indent=2, allow_nan=False))
print(json.dumps({'verified': verified, 'peer_rows': selected,
                  'existing_handoff_exact': True}, indent=2))
