"""Read back the exact published post, artifact bytes and question state."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

Q=Path(__file__).resolve().parents[1]
OUT=Q/'outputs'
POST='post_ecc13cabecf54b789e538f695e4bdca2'

def bio(*args):
    p=subprocess.run(['./bin/bio',*args],check=True,capture_output=True,text=True)
    return json.loads(p.stdout)

post=bio('community','show',POST)
(OUT/'publication-readback.json').write_text(json.dumps(post,indent=2,allow_nan=False)+'\n')
assert post['id']==POST
assert post['author']=='agent_4a2a1e311cb74e98a0101849e6b29f3f'
assert post['content']['body']==(OUT/'publication.md').read_text()
assert post['parent']=='post_569bb436329e46828ed286a26425ab03'
expected={json.loads(p.read_text())['artifact'] for p in (OUT/'registrations').glob('*.registration.json')}
evidence=post['content']['evidence']
assert set(evidence['artifacts'])==expected
assert evidence['notebook']['question']=='q_e835197734394f30'
remote=[]
for p in sorted((OUT/'registrations').glob('*.registration.json')):
    r=json.loads(p.read_text())
    obj=bio('--workspace',str(Path(os.environ['BIO_COMMUNITY'])/'library'),'object','show',r['output_blob'])
    path=Path(obj['path'])
    with path.open('rb') as f:
        assert hashlib.file_digest(f,'sha256').hexdigest()==r['output_blob']
    remote.append({'artifact':r['artifact'],'output_blob':r['output_blob'],'shared_bytes_verified':True})
state=bio('work','show','q_e835197734394f30')
(OUT/'question-final-readback.json').write_text(json.dumps(state,indent=2,allow_nan=False)+'\n')
result={'post':POST,'post_body_verified':True,'artifact_count':len(expected),'shared_artifact_bytes':remote,'published_notebook':evidence['notebook'],'question_readback':'question-final-readback.json'}
(OUT/'publication-verification.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps(result,indent=2))
print('Question state:',json.dumps(state))
