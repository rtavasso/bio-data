"""Read back the exact published target and verify registered-output integrity."""
import hashlib
import json
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
post=json.loads(subprocess.run(['./bin/bio','community','show','post_ede3429c8d7a4485b7681fbf94798066'],capture_output=True,text=True,check=True).stdout)
assert post['author']=='agent_eb57cbb0fb1f4a3897a1cff4713332b8'
assert post['parent']=='post_85b763ee8b6b4ea6bad88cd7f71b48be'
assert post['content']['body']==(OUT/'analysis-post.md').read_text()
regs=[]
for path in sorted((OUT/'registrations').glob('*.json')):
    data=json.loads(path.read_text())
    if 'artifact' in data:
        assert data['conflicting_outputs'] is False
        regs.append(data['artifact'])
assert set(post['content']['evidence']['artifacts'])==set(regs)
receipt=json.loads((OUT/'execution-r001.json').read_text())
for item in receipt['outputs']:
    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
assert hashlib.sha256(Path(receipt['producer']).read_bytes()).hexdigest()==receipt['code_sha256']
(OUT/'publication-readback.json').write_text(json.dumps(post,indent=2))
result={'published_post':post['id'],'body_exact':True,'author_verified':True,'artifacts_verified':len(regs),'producer_unchanged':True,'output_hashes_verified':len(receipt['outputs']),'notebook_snapshot':post['content']['evidence']['notebook']}
(OUT/'final-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
