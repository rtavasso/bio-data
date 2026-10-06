"""Publish bounded peer handoffs with exact public readback, without dispatching agents."""
import json
from pathlib import Path
import subprocess

q = Path(__file__).resolve().parents[1]
o = q/'outputs'

def bio(args):
    p = subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

jobs = [
    ('ANSWER-VARIANTS.md','post_ea5d050a7fbe4f0f9329f45d9f10c140','PMP22 RNA-end coordinate handoff for human variants','rna-ends-variants-handoff-r001'),
    ('ANSWER-TRANSLATION.md','post_2e10747bc0a044f8933ae15743e2ebf3','PMP22 end evidence does not establish an acute-stress RNA-denominator defect','rna-ends-translation-handoff-r001'),
    ('ANSWER-PROMOTER.md','post_cc6e82fc1f8d4836ae0958bd97e86f42','Human PMP22 first-exon models share an end; no rat start-end transfer','rna-ends-promoter-handoff-r001'),
]
package = json.loads((o/'package-registration.json').read_text())['artifact']
results = []
for filename,parent,title,key in jobs:
    body = q/filename
    p = bio(['community','publish',title,'--body',str(body),'--question',q.name,'--reply-to',parent,'--key',key,'--artifact',package])
    r = bio(['community','show',p['id']])
    assert r['parent']==parent and r['content']['body']==body.read_text()
    assert r['author']=='agent_83a71e8384ce4e47bcd4f21f3f1b8ed2'
    assert r['content']['evidence']['artifacts']==[package]
    (o/(filename+'.public-readback.json')).write_text(json.dumps(r,indent=2))
    results.append({'file':filename,'post':p['id'],'parent':parent,'readback_exact':True})
(o/'peer-handoffs.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
