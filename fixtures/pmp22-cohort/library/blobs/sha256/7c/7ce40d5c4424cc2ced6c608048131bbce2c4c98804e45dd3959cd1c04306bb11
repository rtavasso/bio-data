"""Read-only community discovery and evidence index; never execute inherited code."""
import json
import os
from pathlib import Path
import subprocess

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'inputs' / 'prior'
OUT.mkdir(parents=True, exist_ok=True)
LIB = Path(os.environ['BIO_COMMUNITY']) / 'library'

def cli(args, label):
    result = subprocess.run(['./bin/bio', *args], capture_output=True, text=True, check=True)
    (OUT / f'{label}.json').write_text(result.stdout)
    return json.loads(result.stdout)

queries = ['miR-29', 'IRE1', 'AGO2', 'Dicer', 'G3BP', 'RNA stability', 'ribosome', 'GSE103957', 'PMP22']
for n, term in enumerate(queries):
    result = cli(['community', 'search', '--text', term, '--limit', '100'], f'forum-{n}')
    print(term, 'total=', result['total'], 'next=', result.get('next_offset'))
    for item in result['items']:
        print(' ', item['subject'], item['title'], 'superseded=', item.get('superseded_by'))
for command in ['artifact', 'work', 'data']:
    result = cli(['--workspace', str(LIB), command, 'search', '--text', 'RNA'], f'library-{command}')
    print('LIBRARY', command, result.get('total'))
    for item in result.get('items', []):
        print(' ', item.get('subject'), item.get('title'))
for h, label in [('e054cae33492c105e41221766e86dc067d7c5dfeaf75fc8409c23b468964166b', 'notebook-manifest'), ('ec40eba9a7bdd48c792a6163e7a40a9e4105cdc5aadc492977bbaf42f9eea2a3', 'prior-package'), ('043b8a66d39ab07ff0ad7ad179e3d13e36e6c88f5b480d4f3d25f6e43ebe287e', 'mechanism-map')]:
    p = LIB / 'blobs' / 'sha256' / h[:2] / h
    data = json.loads(p.read_text())
    (OUT / f'{label}.json').write_text(json.dumps(data, indent=2))
    print(label, 'keys=', list(data))
    if label == 'mechanism-map':
        for edge in data['edges']:
            if any(word in json.dumps(edge).lower() for word in ['mir', 'ire1', 'g3bp', 'dicer', 'footprint']):
                print(json.dumps(edge, indent=2))
    if label == 'prior-package':
        print(json.dumps(data, indent=2)[:6500])
