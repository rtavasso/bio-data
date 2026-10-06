"""Display non-body publication fields; do not infer response schemas."""
import json
import os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
p=json.loads((q/'outputs/publication.json').read_text())
print('TOP_KEYS',list(p))
for k,v in p.items():
    if not isinstance(v,(dict,list)):
        print(k,json.dumps(v))
    elif k!='content':
        print(k,json.dumps(v))
if isinstance(p.get('content'),dict):
    print('CONTENT_KEYS',list(p['content']))
    for k,v in p['content'].items():
        if k!='body':
            print('content.'+k,json.dumps(v))
