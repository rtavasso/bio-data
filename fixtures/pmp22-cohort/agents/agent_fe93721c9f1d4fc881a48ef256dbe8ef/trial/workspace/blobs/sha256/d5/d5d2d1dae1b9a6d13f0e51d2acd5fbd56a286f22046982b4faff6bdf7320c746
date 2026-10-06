"""Correct unsupported browser attribution; preserve scientific results byte-for-byte."""
import hashlib
import json
import zipfile
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
original = out / 'EGR2-PMP22-mediation-audit.zip'
assert hashlib.sha256(original.read_bytes()).hexdigest() == '100b9b8c6a76dbee93a7330a95b3be61a1c7397e4488981bc0dd432f6d35f241'
replace = ['LABBOOK.md', 'outputs/REPORT.md', 'inputs/browser-checks.json']
with zipfile.ZipFile(original) as z:
    members = {name: z.read(name) for name in z.namelist() if name != 'bundle-manifest.json'}
for name in replace:
    members[name] = (q / name).read_bytes()
protected = ['outputs/GSE201623-audit.json', 'outputs/GSE201623-target-audit.tsv', 'outputs/GSE201623-all-effects.tsv',
             'outputs/GSE201623-sample-eligibility.json', 'outputs/intervention-by-endpoint.tsv', 'outputs/assay-eligibility.json',
             'outputs/mediation-audit.json', 'inputs/interventions.curated.json', 'inputs/rescue-test.json']
assert all(members[name] == (q / name).read_bytes() for name in protected)
correction = {'status': 'browser_provenance_retracted', 'replaces_archive_artifact': 'artifact_0e97fd2932f209820af010da8872510c1c33f17a25a2eb8605f3969fa43f5bc6',
              'reason': 'Unsupported browser ledger/reference identifiers withdrawn. Direct HTTP and inherited primary-source receipts remain evidence. No claimed browser corroboration.',
              'scientific_output_bytes_unchanged': protected, 'replaced_members': replace,
              'original_archive_sha256': hashlib.sha256(original.read_bytes()).hexdigest()}
(out / 'provenance-correction.json').write_text(json.dumps(correction, indent=2, allow_nan=False) + '\n')
members['provenance-correction.json'] = (out / 'provenance-correction.json').read_bytes()
members['scripts/build_corrected_bundle.py'] = Path(__file__).read_bytes()
manifest = {'question': q.name, 'revision': 2, 'correction': correction,
            'files': [{'path': k, 'bytes': len(v), 'sha256': hashlib.sha256(v).hexdigest()} for k, v in sorted(members.items())]}
(out / 'bundle-manifest.r002.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
members['bundle-manifest.r002.json'] = (out / 'bundle-manifest.r002.json').read_bytes()
archive = out / 'EGR2-PMP22-mediation-audit.r002.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for name, content in members.items():
        z.writestr(name, content)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None and len(z.namelist()) == len(members)
    for member in manifest['files']:
        assert hashlib.sha256(z.read(member['path'])).hexdigest() == member['sha256']
print(json.dumps({'archive': str(archive), 'verified_members': len(members), 'bytes': archive.stat().st_size,
                  'science_unchanged': True, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}))
