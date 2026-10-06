"""Read-only inspection of published context; never executes inherited code."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'inputs' / 'community'
OUT.mkdir(parents=True, exist_ok=True)

def cli(*args):
    p = subprocess.run(['./bin/bio', *args], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)

for term in ['PMP22', 'UGGT1', 'RER1', 'calnexin', 'trafficking', 'proteasome', 'surface', 'PMC8191293', 'PMC4227013', 'PXD043917']:
    data = cli('community', 'search', '--text', term, '--limit', '100')
    (OUT / f'search-{term}.json').write_text(json.dumps(data, indent=2))
    print(term, 'total', data['total'], 'next', data.get('next_offset'))
    for item in data['items']:
        print(' ', item['subject'], item['title'], 'superseded', item.get('superseded_by'))
for name in ['e054cae33492c105e41221766e86dc067d7c5dfeaf75fc8409c23b468964166b', 'ec40eba9a7bdd48c792a6163e7a40a9e4105cdc5aadc492977bbaf42f9eea2a3']:
    obj = cli('--workspace', os.environ['BIO_COMMUNITY'] + '/library', 'object', 'show', name)
    data = json.loads(Path(obj['path']).read_text())
    (OUT / f'{name}.pretty.json').write_text(json.dumps(data, indent=2))
    print(name, 'keys', list(data))
