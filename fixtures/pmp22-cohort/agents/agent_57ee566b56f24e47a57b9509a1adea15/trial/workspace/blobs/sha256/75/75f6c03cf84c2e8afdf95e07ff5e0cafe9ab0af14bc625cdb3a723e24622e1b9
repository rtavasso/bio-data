"""Compact public-source manifests; no outcome calculations."""
import json,os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
for name in ['resolve-GSE216665','repair-assets','inherited-state-manifest','repair-source-current']:
    x=json.loads((q/f'outputs/{name}.json').read_text())
    (q/f'outputs/{name}.pretty.json').write_text(json.dumps(x,indent=2))
    if name.startswith('resolve'): print(name,{k:v for k,v in x.items() if k!='assets'})
    elif name=='repair-assets':
        print('ASSETS_KEYS',list(x))
        for row in x.get('items',[]): print(row)
    elif name=='inherited-state-manifest':
        print('STATE_MANIFEST',x.get('output_blob'),x.get('path')); print(x['manifest']['derivation']['inputs'])
