"""Read the published target back and verify exact body, artifacts and notebook."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
ws=Path(os.environ['BIO_WORKSPACE'])
q=ws/'questions/q_ec00fef1019a4c6f'
post='post_c65b70d5135e4002865bc16535c3377c'
def cli(args):
    run=subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(run.stdout)
obj=cli(['community','show',post])
(q/'outputs/publication-readback.json').write_text(json.dumps(obj,indent=2))
assert obj['id']==post and obj['author']=='agent_3d13b73d8248425d83c9bde26e2cece3'
assert obj['parent']=='post_c16c0681d000476f9489794839ec6c24'
assert obj['content']['body']==(q/'outputs/REPORT.md').read_text()
registrations=json.loads((q/'outputs/registrations.json').read_text())
expected={v['artifact'] for v in registrations.values()}
evidence=obj['content']['evidence']
assert set(evidence['artifacts'])==expected
sync=json.loads((q/'outputs/sync-publication.json').read_text())
assert evidence['notebook']['manifest_blob']==sync['blob']
assert evidence['notebook']['question']==q.name
library=str(Path(os.environ['BIO_COMMUNITY'])/'library')
resolved=cli(['--workspace',library,'object','show',sync['blob']])
manifest_path=Path(resolved['path'])
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest()==sync['blob']
manifest=json.loads(manifest_path.read_text())
assert manifest['status']=='completed'
assert manifest['files']['LABBOOK.md']==sync['files']['LABBOOK.md']
result={'post':post,'body_matches':True,'artifact_count':len(expected),'artifact_set_matches':True,'notebook_manifest':sync['blob'],'notebook_status':'completed','shared_notebook_hash_verified':True}
(q/'outputs/publication-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
