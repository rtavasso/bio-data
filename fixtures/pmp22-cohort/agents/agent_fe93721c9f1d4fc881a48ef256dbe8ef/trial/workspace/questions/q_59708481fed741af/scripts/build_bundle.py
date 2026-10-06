"""Assemble a portable audit archive, preserving agent attribution and actual receipts."""
import hashlib
import json
import zipfile
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
files = [q / 'LABBOOK.md', q / 'QUESTION.md']
files += sorted((q / 'scripts').glob('*.py'))
files += sorted((q / 'scripts').glob('*.swift'))
files += sorted((q / 'inputs').glob('*.json'))
files += sorted((q / 'inputs/public').glob('*.receipt.json'))
names = ['REPORT.md', 'intervention-by-endpoint.tsv', 'assay-eligibility.json', 'mediation-audit.json',
         'GSE201623-audit.json', 'GSE201623-target-audit.tsv', 'GSE201623-all-effects.tsv',
         'GSE201623-sample-eligibility.json', 'nondecimal-count-tokens.json', 'registrations.json',
         'PMC11014456.source.txt', 'PMC11592338.source.txt', 'PMC5800313.source.txt', 'nae1-figure-OCR.json']
files += [out / name for name in names]
for pattern in ['rna-execution-r00*', 'audit-execution-r001*', 'nae1-ocr-page-*.txt']:
    files += sorted(out.glob(pattern))
assert len(files) == len(set(files))
manifest = {'question': q.name, 'author': 'agent_2a95fafb692f4546b628ba410393d5b1',
            'type': 'Archive assembly, not an independent biological analysis',
            'registration_sources': json.loads((out / 'registrations.json').read_text()),
            'primary_source_hashes': json.loads((q / 'inputs/interventions.curated.json').read_text())['sources'],
            'files': [{'path': str(p.relative_to(q)), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
(out / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
archive = out / 'EGR2-PMP22-mediation-audit.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, str(p.relative_to(q)))
    z.write(out / 'bundle-manifest.json', 'bundle-manifest.json')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for entry in manifest['files']:
        assert hashlib.sha256(z.read(entry['path'])).hexdigest() == entry['sha256']
    assert len(z.namelist()) == len(files) + 1
print(json.dumps({'archive': str(archive), 'verified_members': len(files) + 1, 'bytes': archive.stat().st_size,
                  'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}))
