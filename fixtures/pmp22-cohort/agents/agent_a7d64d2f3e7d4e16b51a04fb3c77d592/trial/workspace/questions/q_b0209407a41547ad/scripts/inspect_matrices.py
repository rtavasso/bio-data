"""Inspect native matrix structure and source-labelled sample units."""
import gzip
import importlib.metadata
import json
from pathlib import Path
import sys
import textwrap

Q = Path(__file__).resolve().parents[1]
for package in ['numpy', 'pandas', 'scipy', 'openpyxl']:
    try:
        print(package, importlib.metadata.version(package))
    except importlib.metadata.PackageNotFoundError:
        print(package, 'not installed')
for label, acc in [('Acly', 'GSE252209'), ('CMT', 'GSE115930')]:
    a = json.loads((Q / 'outputs' / f'{label}-acquired.json').read_text())
    print(label, 'PATH', a['path'])
    with gzip.open(a['path'], 'rt') as f:
        for _ in range(4):
            print(f.readline().strip()[:1800])
    doc = json.loads((Q / 'outputs' / f'{acc}-metadata.json').read_text())
    seen = {}
    for profile in doc['profiles']:
        for ctx in profile.get('facts', {}).get('related_source_context', []):
            if ctx['kind'] == 'sample':
                fields = ctx['body']['fields']
                key = ctx['native_id']
                if key not in seen:
                    seen[key] = {k: v for k, v in fields.items() if k in ['Sample_title','Sample_characteristics_ch1','Sample_source_name_ch1','Sample_description','Sample_data_processing','Sample_extract_protocol_ch1','Sample_growth_protocol_ch1']}
    (Q / 'outputs' / f'{acc}-sample-metadata.json').write_text(json.dumps(seen, indent=2))
    for sid, x in seen.items():
        print(sid, x['Sample_title'], x.get('Sample_characteristics_ch1'), x.get('Sample_description'))
    print('FIRST METHODS', next(iter(seen.values())))
if len(sys.argv) > 1:
    doc = json.loads((Q / 'inputs/PMC11660526-bioc.json').read_text())
    blocks = []
    for collection in doc:
        for article in collection['documents']:
            for p in article['passages']:
                blocks.append(f'[{p["offset"]} {p["infons"]}]\n' + textwrap.fill(p.get('text', ''), 120))
    (Q / 'outputs/PMC11660526-bioc.txt').write_text('\n\n'.join(blocks))
    print('BIOC paragraphs', len(blocks))
