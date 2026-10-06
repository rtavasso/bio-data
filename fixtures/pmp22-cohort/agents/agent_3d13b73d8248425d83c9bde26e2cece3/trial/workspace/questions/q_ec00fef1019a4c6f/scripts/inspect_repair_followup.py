"""Inspect prior forum overlap and immutable inputs before a focused source audit."""
import json
import os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
for name in ['repair','selectivity','dissociation']:
    obj=json.loads((q/f'outputs/followup-forum-{name}.json').read_text())
    print('SEARCH',name,'total',obj['total'],'next_offset',obj['next_offset'])
    for x in obj['items']:
        print(x['subject'],x['title'], 'superseded_by',x.get('superseded_by'))
p=json.loads((q/'outputs/followup-peer-proposal.json').read_text())
print('PEER',p['id'],p['author'],p['content']['body'])
print('PEER_EVIDENCE',json.dumps(p['content']['evidence'],indent=2))
a=json.loads((q/'outputs/followup-audit-manifest.json').read_text())
print('AUDIT_KEYS',list(a))
print('AUDIT',json.dumps(a,indent=2))
for entry in json.loads((q/'outputs/followup-agents.json').read_text()):
    if '57ee566b56f24e47a57b9509a1adea15' in json.dumps(entry):
        print('ASKER_CURRENT_STATUS',json.dumps(entry))
