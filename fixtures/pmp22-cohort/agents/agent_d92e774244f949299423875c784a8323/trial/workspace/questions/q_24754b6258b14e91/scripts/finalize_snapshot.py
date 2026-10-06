"""Verify shared artifact bytes and resync the completed notebook without changing science."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
Q=Path(__file__).resolve().parents[1];ROOT=Q.parents[2]
shared=Path(os.environ['BIO_COMMUNITY'])/'library/blobs/sha256'
v=json.loads((Q/'outputs/publication-validation.json').read_text())
for r in v['artifacts']:
    h=r['sha256'];p=shared/h[:2]/h
    assert hashlib.sha256(p.read_bytes()).hexdigest()==h
checks={'publication':v['publication'],'shared_artifact_count':len(v['artifacts']),'all_shared_sha256_passed':True}
with (Q/'outputs/shared-byte-verification.json').open('x') as f:json.dump(checks,f,indent=2)
def bio(*args):
    return json.loads(subprocess.run(['./bin/bio',*map(str,args)],cwd=ROOT,text=True,capture_output=True,check=True).stdout)
s=bio('work','sync',Q.name,'--status','completed','--summary',
 'Published post_23179ccab3454895a63656d4119fdef0;16 shared artifact blobs verified. Human first-exon-linked sQTL candidate; GENCORD non-replication and exact-splice validation gap retained. No pending scientific dependency.')
w=bio('work','show',Q.name)
assert w['status']=='completed'
h=hashlib.sha256((Q/'LABBOOK.md').read_bytes()).hexdigest()
assert w['snapshot']['files']['LABBOOK.md']==h==s['files']['LABBOOK.md']
for name,obj in [('completed-sync-r002.json',s),('completed-work-readback-r002.json',w)]:
    with (Q/'inputs/community'/name).open('x') as f:json.dump(obj,f,indent=2)
print(json.dumps(dict(checks,notebook_hash_verified=h,work_status=w['status'],snapshot=w['current_work'])))
