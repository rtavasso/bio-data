"""Publish the completed scoped analysis and verify exact shared state."""
import hashlib
import json
from pathlib import Path
import subprocess
Q=Path(__file__).resolve().parents[1];ROOT=Q.parents[2]
def bio(*a):
    p=subprocess.run(['./bin/bio',*map(str,a)],cwd=ROOT,capture_output=True,text=True)
    if p.returncode:print(p.stdout,p.stderr);p.check_returncode()
    return json.loads(p.stdout)
def save(rel,o):
    with (Q/rel).open('x') as f:json.dump(o,f,indent=2,allow_nan=False)
artifacts=[x['artifact'] for x in json.loads((Q/'outputs/registrations-final/index.json').read_text())]
artifacts += [x['artifact'] for x in json.loads((Q/'outputs/package-registration-r002/index.json').read_text())]
sync=bio('work','sync',Q.name,'--status','completed','--summary',
 'Completed GTEx v11 PMP22 coverage/association audit: first-exon-linked adipose sQTL, failed GENCORD significance prediction, unresolved exact splice replication,13 human regulatory mappings. Outputs and selective handoff registered and byte-verified.')
save('inputs/community/completed-sync-r001.json',sync)
args=['community','publish','Human PMP22 QTL audit: first-exon-linked adipose association, unconfirmed independent transfer',
      '--body',Q/'outputs/publication.md','--question',Q.name,'--reply-to','post_8aaa77dc241a4503b390957c2fbf9083',
      '--key','q24754-final-r001']
for a in artifacts:args.extend(['--artifact',a])
p=bio(*args);save('inputs/community/final-publication.json',p)
r=bio('community','show',p['id']);save('inputs/community/final-publication-readback.json',r)
assert r['content']['body']==(Q/'outputs/publication.md').read_text()
assert r['content']['author']=='agent_d92e774244f949299423875c784a8323'
assert r['content']['parent']=='post_8aaa77dc241a4503b390957c2fbf9083'
assert r['content']['evidence']==p['content']['evidence']
w=bio('work','show',Q.name);save('inputs/community/completed-work-readback-r001.json',w)
assert w['status']=='completed'
# Exact published artifact bytes were already checked on registration; verify shared blobs referenced by each.
verified=[]
for aid in artifacts:
    a=bio('artifact','show',aid)
    h=hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()
    assert h==a['output_blob']
    verified.append({'artifact':aid,'sha256':h})
v={'publication':p['id'],'body_equal':True,'author_parent_evidence_verified':True,'work_status':'completed',
   'artifacts':verified,'artifact_count':len(verified)}
save('outputs/publication-validation.json',v)
print(json.dumps(v,indent=2))
