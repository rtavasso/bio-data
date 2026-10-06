"""Inspect saved JSON metadata/CLI logs without running downloaded code."""
import json
from pathlib import Path
Q = Path(__file__).resolve().parents[1]
ROOT = Q.parents[2]
api = json.loads((Q/'inputs/public/gtex-openapi.json').read_text())
print('API', api.get('info'))
for path, ops in api['paths'].items():
    if any(s in path.lower() for s in ['eqtl','sqtl','dataset','download','gene','tissue']):
        print(path)
        for op in ops.values():
            if isinstance(op, dict):
                print(op.get('summary'), [(p['name'], p.get('schema')) for p in op.get('parameters',[])])
                print(str(op.get('description',''))[:1800])
for fn in ['out-1791235989-1058-3a80.log', 'out-1791236005-1058-1940.log']:
    rows = []
    for line in (ROOT/'.hermes/cache/terminal-output'/fn).read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    p=Q/'inputs/community'/f'{fn}.json'
    if not p.exists():
        p.write_text(json.dumps(rows, indent=2, allow_nan=False))
    for obj in rows:
        if isinstance(obj,dict) and 'items' in obj:
            print('SAVED SEARCH', obj['query'], obj['total'])
            for x in obj['items']:
                print(x['subject'], x['title'])
