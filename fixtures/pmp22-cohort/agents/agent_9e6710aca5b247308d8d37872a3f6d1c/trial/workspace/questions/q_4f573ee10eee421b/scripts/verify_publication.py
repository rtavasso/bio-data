"""Verify the exact shared publication, source/output bytes and completed state."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q/'outputs'
POST = 'post_639d9e2370204ce089ce503c183bd2d4'

def bio(*args):
    p = subprocess.run(['./bin/bio',*args],check=True,capture_output=True,text=True)
    return json.loads(p.stdout)

def verify_shared(digest):
    obj = bio('--workspace',str(Path(os.environ['BIO_COMMUNITY'])/'library'),'object','show',digest)
    with Path(obj['path']).open('rb') as f:
        assert hashlib.file_digest(f,'sha256').hexdigest()==digest

post = bio('community','show',POST)
(OUT/'publication-readback.json').write_text(json.dumps(post,indent=2,allow_nan=False)+'\n')
assert post['id']==POST
assert post['author']=='agent_9e6710aca5b247308d8d37872a3f6d1c'
assert post['parent']=='post_2380b4bbde9a4d218e38d4a6dfe9670f'
assert post['content']['body']==(OUT/'publication.md').read_text()
receipts=[json.loads(p.read_text()) for p in sorted((OUT/'registrations').glob('*.registration.json'))]
expected={r['artifact'] for r in receipts}
assert len(expected)==len(receipts)==10
assert set(post['content']['evidence']['artifacts'])==expected
assert post['content']['evidence']['notebook']['question']=='q_4f573ee10eee421b'
for r in receipts:
    assert not r['conflicting_outputs'] and r['warning'] is None
    verify_shared(r['output_blob'])
source_hashes={x['blob'] for x in json.loads((Q/'inputs/acquisition/manifest.json').read_text())}
for digest in source_hashes:
    verify_shared(digest)
state=bio('work','show','q_4f573ee10eee421b')
assert state['status']=='completed'
(OUT/'question-final-readback.json').write_text(json.dumps(state,indent=2,allow_nan=False)+'\n')
result={'post':POST,'post_body_parent_author_verified':True,'artifact_count':len(expected),'all_shared_output_hashes_verified':True,'shared_native_processed_files_verified':len(source_hashes),'question_status':state['status'],'published_notebook':post['content']['evidence']['notebook'],'evidence_manifest':post['content']['evidence']['manifest_blob'],'scope':'publication and byte integrity, not independent biological replication'}
(OUT/'publication-verification.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps(result,indent=2))
