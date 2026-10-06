"""Package selected immutable evidence and verify every ZIP member; no scientific rerun."""
import hashlib
import json
import os
from pathlib import Path
import zipfile

Q = Path(__file__).resolve().parents[1]
WS = Path(os.environ['BIO_WORKSPACE']).resolve()
OUT = Q / 'outputs'
manifest = json.loads((Q / 'inputs/immutable-inputs.json').read_text())
content = {}
for r in manifest['inputs']:
    data = (WS / 'blobs/sha256' / r['blob'][:2] / r['blob']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == r['blob']
    assert len(data) == r['bytes']
    content[r['relative_path']] = data
# Preserve smaller original response bodies, including unsuccessful ones, matched to receipts.
receipt_checks = []
for rp in sorted((Q / 'inputs/public').glob('*.receipt.json')):
    receipt = json.loads(rp.read_text())
    payload = rp.with_name(rp.name.removesuffix('.receipt.json'))
    if not payload.exists():
        raise FileNotFoundError(payload)
    data = payload.read_bytes()
    assert hashlib.sha256(data).hexdigest() == receipt['sha256']
    assert len(data) == receipt['bytes']
    if payload.suffix != '.zip':
        content[str(payload.relative_to(Q))] = data
    receipt_checks.append({'payload': str(payload.relative_to(Q)),
                           'sha256': receipt['sha256'], 'bytes': len(data),
                           'status': receipt['status'],
                           'included_payload': payload.suffix != '.zip'})
# Validate native workbook directly against its transport archive.
workbook_name = 'inputs/native/PMC10684506/43856_2023_400_MOESM2_ESM.xlsx'
with zipfile.ZipFile(Q / 'inputs/public/PMC10684506-supp.zip') as z:
    assert z.read(Path(workbook_name).name) == content[workbook_name]
paths = [Q / 'LABBOOK.md', Q / 'inputs/immutable-inputs.json']
paths += list((Q / 'outputs/r002').glob('*'))
paths += list((Q / 'outputs/registrations').glob('*.json'))
paths += list((Q / 'scripts').glob('*.py'))
paths += list((Q / 'outputs').glob('execution-r00[12].json*'))
# Keep previous source-line representation and unmodified original producer/output receipt.
paths += [Q / 'outputs/GSE7423-donor-channel-map.tsv']
for path in sorted(set(paths)):
    name = str(path.relative_to(Q))
    assert path.is_file() and not path.is_symlink()
    content[name] = path.read_bytes()
for version in ('r001', 'r002'):
    receipt = json.loads(content[f'outputs/execution-{version}.json'])
    assert receipt['exit_code'] == 0 and receipt['complete']
    code_name = 'scripts/audit_human_dosage.py' if version == 'r002' else 'scripts/audit_human_dosage-r001.py'
    assert hashlib.sha256(content[code_name]).hexdigest() == receipt['code_sha256']
    for output in receipt['outputs']:
        path = Q / 'outputs' / (f'r002/{Path(output["path"]).name}' if version == 'r002' else Path(output['path']).name)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == output['sha256']
        if version == 'r002':
            assert str(path.relative_to(Q)) in content
members = [{'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
           for name, data in sorted(content.items())]
share_manifest = {'question': Q.name, 'members': members,
                  'scope': 'Selected primary bytes, original retrieval receipts, manual annotations, measured values, actual producer receipts and registration records; excludes large supplementary transport ZIPs/videos.',
                  'HTTP_receipt_checks': receipt_checks,
                  'workbook_parent_member_verified': True,
                  'source_path_note': 'Paths are question-relative except historical receipt fields. Never execute inherited code, macros, formulas or serializations.'}
manifest_bytes = (json.dumps(share_manifest, indent=2, allow_nan=False) + '\n').encode()
with (OUT / 'human-dosage-handoff-manifest.json').open('xb') as f:
    f.write(manifest_bytes)
archive = OUT / 'human-dosage-handoff.zip'
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
    for name, data in sorted(content.items()):
        zi = zipfile.ZipInfo(name)
        zi.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(zi, data)
    z.writestr('share-manifest.json', manifest_bytes)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert set(z.namelist()) == set(content) | {'share-manifest.json'}
    assert z.read('share-manifest.json') == manifest_bytes
    for row in members:
        assert z.read(row['path']) == content[row['path']]
result = {'status': 'passed', 'members_excluding_embedded_manifest': len(members),
          'members_total': len(members) + 1, 'bytes': archive.stat().st_size,
          'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
          'HTTP_receipts_validated': len(receipt_checks), 'original_and_final_producer_receipts_verified': True,
          'zip_crc_and_all_member_byte_checks': True,
          'scientific_reanalysis': False}
with (OUT / 'human-dosage-handoff-validation.json').open('x') as f:
    json.dump(result, f, indent=2, allow_nan=False)
    f.write('\n')
print(json.dumps(result, indent=2))
