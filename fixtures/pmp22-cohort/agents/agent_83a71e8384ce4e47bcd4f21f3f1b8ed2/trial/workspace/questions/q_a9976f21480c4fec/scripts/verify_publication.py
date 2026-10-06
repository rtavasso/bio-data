"""Read back the exact public targets and validate publication content/evidence."""
import json
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]
o=q/'outputs'

def cli(args):
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

expected=json.loads((o/'publication-result.json').read_text())
post=cli(['community','show',expected['id']])
assert post['id']==expected['id']
assert post['content']['body']==(q/'PUBLICATION-WITH-ARTIFACTS.md').read_text()
assert post['author']=='agent_53839439c0344c80835201ae0e28eb5c'
assert post['parent']=='post_85b763ee8b6b4ea6bad88cd7f71b48be'
assert post['content']['evidence']['artifacts']==expected['content']['evidence']['artifacts']
assert len(post['content']['evidence']['artifacts'])==6
(o/'publication-readback.json').write_text(json.dumps(post,indent=2))
inbox=cli(['community','inbox'])
(o/'final-inbox.json').write_text(json.dumps(inbox,indent=2))
sync=cli(['work','sync',q.name,'--status','completed','--summary','Published and verified post_1b2c4f75fb614dd7931820b681db11d7 with six corrected artifacts; evidence/assay matrices, source bytes and rate non-identifiability preserved.'])
(o/'final-sync.json').write_text(json.dumps(sync,indent=2))
work=cli(['work','show',q.name])
(o/'final-work-readback.json').write_text(json.dumps(work,indent=2))
assert 'completed' in json.dumps(work)
print(json.dumps({'post':post['id'],'body_verified':True,'artifact_count':6,'notebook_completed':True,'inbox':inbox},allow_nan=False))
