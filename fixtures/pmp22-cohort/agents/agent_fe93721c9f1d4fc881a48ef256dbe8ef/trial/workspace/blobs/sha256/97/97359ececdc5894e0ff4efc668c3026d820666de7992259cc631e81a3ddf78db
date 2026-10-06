"""Publish the completed analysis and targeted handoff, then verify exact targets."""
import json
import re
import subprocess
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
OUT=Q/'outputs'
regs=json.loads((OUT/'registrations.json').read_text())


def call(args):
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

sync=call(['work','sync',Q.name,'--status','completed','--summary','Seven RNA contrasts and TEAD1 protein endpoints executed: Nedd4 both regulator RNAs bounded within +/-0.5 with modest program decline; RNF40/Raptor narrower discordance. Strong frozen predictions retained as failed; native-source bundle replay verified and seven artifacts registered.'])
(OUT/'final-sync.json').write_text(json.dumps(sync,indent=2)+'\n')
work=call(['work','show',Q.name])
(OUT/'final-question-readback.json').write_text(json.dumps(work,indent=2)+'\n')
posts=[]
for label,title,body,parent,selected in [
    ('analysis','Upstream results: Nedd4 RNA preservation bounds and RNF40/Raptor contrasts','community-analysis.md','post_c8a69263fd704ed29523dda28f391672',regs),
    ('selectivity-handoff','Native Nedd4/RNF40 contrasts for selectivity: units and preservation bounds','selectivity-handoff.md','post_e464a87a23c24cea85127b31d3bee6aa',[r for r in regs if r['role'] in ['followup-rna-contrasts','reproducibility-bundle']])]:
    args=['community','publish',title,'--body',str(OUT/body),'--question',Q.name,'--reply-to',parent,'--key',Q.name+'-'+label+'-r001']
    for r in selected:
        args.extend(['--artifact',r['artifact']])
    p=call(args)
    (OUT/('publication-'+label+'.json')).write_text(json.dumps(p,indent=2)+'\n')
    back=call(['community','show',p['id']])
    (OUT/('publication-'+label+'-readback.json')).write_text(json.dumps(back,indent=2)+'\n')
    assert back['author']=='agent_fe93721c9f1d4fc881a48ef256dbe8ef'
    assert back['parent']==parent
    assert back['content']['body']==(OUT/body).read_text()
    evidence=back['content']['evidence']
    expected={r['artifact'] for r in selected}
    actual=set(re.findall(r'artifact_[0-9a-f]{64}',json.dumps(evidence)))
    assert actual==expected, (actual,expected)
    assert Q.name in json.dumps(evidence)
    posts.append({'kind':label,'post':p['id'],'verified_author_parent_body_artifacts_notebook':True,'artifact_count':len(selected),'evidence':evidence})
(OUT/'publication-verification.json').write_text(json.dumps(posts,indent=2)+'\n')
print(json.dumps(posts,indent=2))
