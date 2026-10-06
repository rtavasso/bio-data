"""Read only selected local/peer provenance; never execute inherited code."""
import hashlib
import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
old = w / 'questions/q_277f20df4b6b47cc'
peer = json.loads((q / 'inputs/peer-disposition-local.json').read_text())
p = w / 'blobs/sha256' / peer['output_blob'][:2] / peer['output_blob']
assert hashlib.sha256(p.read_bytes()).hexdigest() == peer['output_blob']
print('PEER DISPOSITION TABLE (inherited research content)')
print(p.read_text())
reg = json.loads((old / 'outputs/continuation-registration.json').read_text())
print('ORIGINAL REGISTRATIONS')
print(json.dumps({k: v for k, v in reg['outputs'].items() if k.startswith('protein-')}, indent=2))
previous = json.loads((q / 'inputs/previous-state-work.json').read_text())
print('PREVIOUS STATE QUESTION TOP LEVEL KEYS', list(previous))
for key in previous:
    if key not in ('question', 'notebook', 'artifacts', 'labbook', 'manifest'):
        print(key, json.dumps(previous[key], indent=2))
print('PROTEOSTASIS PUBLICATION BODY')
print(json.loads((q / 'inputs/peer-publication.json').read_text())['content']['body'])
