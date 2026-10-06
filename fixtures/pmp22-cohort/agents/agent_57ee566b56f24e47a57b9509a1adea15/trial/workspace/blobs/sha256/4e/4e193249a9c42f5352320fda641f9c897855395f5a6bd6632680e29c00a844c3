"""Inspect actual publication schema before exact verification."""
import json,os,subprocess
from pathlib import Path
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';O=Q/'outputs'
for name in ['final-publication','rbp-coverage-publication','lipid-critique-publication']:
    x=json.loads((O/f'{name}.json').read_text())
    r=subprocess.run(['./bin/bio','community','show',x['id']],capture_output=True,text=True,check=True);y=json.loads(r.stdout);(O/f'{name}-readback.json').write_text(json.dumps(y,indent=2))
    print(name,y['id'],y['author'],y['parent'],json.dumps(y['content'].get('evidence',{})))
sync=json.loads((O/'sync-completed.json').read_text());print('SYNC',sync)
r=subprocess.run(['./bin/bio','work','show','q_6a3a0a07fa5d4da1'],capture_output=True,text=True,check=True);x=json.loads(r.stdout);(O/'completed-work-readback.json').write_text(json.dumps(x,indent=2));print('WORK_KEYS',list(x));print('WORK',x.get('status'),x.get('id'))
