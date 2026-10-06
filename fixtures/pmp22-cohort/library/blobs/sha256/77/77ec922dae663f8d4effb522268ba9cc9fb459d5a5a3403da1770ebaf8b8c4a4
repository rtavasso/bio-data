"""Compact CLI receipts/discovery data and verify posted proposal/question by exact readback."""
import json, os, subprocess
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
for name in ['proposal-publish','ask-parent']:
    x=json.loads((q/f'outputs/{name}.json').read_text())
    print(name, {k:v for k,v in x.items() if not isinstance(v,(dict,list))})
    if name=='proposal-publish':
        r=subprocess.run(['./bin/bio','community','show',x['id']],capture_output=True,text=True,check=True)
        y=json.loads(r.stdout); assert y['content']['body']==(q/'outputs/early-proposal.md').read_text()
        (q/'outputs/proposal-readback.json').write_text(json.dumps(y,indent=2))
        print('PROPOSAL_READBACK_OK',y['id'])
for p in sorted((q/'outputs').glob('discovery-*.json')):
    x=json.loads(p.read_text()); print('\n',p.name, 'keys', list(x) if isinstance(x,dict) else type(x).__name__)
    (p.with_suffix('.pretty.json')).write_text(json.dumps(x,indent=2))
    print(json.dumps(x)[:6000])
