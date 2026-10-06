"""Read back exact publications/artifact links and save an administrative receipt."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]

def cli(args):
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True)
    p.check_returncode()
    return json.loads(p.stdout)

checks=[]
posts=[('post_dde63c32ed55489bbe21572656f01c22','INDEPENDENT-PUBLICATION.md'),('post_1698da9b00254105913582883fecd721','PEER-SITE-HANDOFF.md')]
for receipt,local in [('selective-publication.json','SELECTIVE-HANDOFF.md'),('translation-publication.json','TRANSLATION-HANDOFF.md')]:
    saved=json.loads((q/'outputs'/receipt).read_text())
    posts.append((saved['id'],local))
for post,local in posts:
    data=cli(['community','show',post])
    body=(q/local).read_text()
    assert data['content']['body']==body
    assert data['author']==os.environ['BIO_AGENT']
    stored=cli(['--workspace',str(Path(os.environ['BIO_COMMUNITY'])/'library'),'object','show',data['body_blob']])
    native=Path(stored['path']).read_bytes()
    assert hashlib.sha256(native).hexdigest()==data['body_blob']
    assert json.loads(native)['body']==body  # body_blob stores the complete post JSON, not bare prose.
    checks.append({'post':post,'post_content_blob':data['body_blob'],'body_text_sha256':hashlib.sha256(body.encode()).hexdigest(),'artifacts':data['content']['evidence']['artifacts'],'verified':True})
for item in json.loads((q/'outputs/followup-artifacts.json').read_text()):
    data=cli(['artifact','show',item['artifact']])
    assert data['output_blob']==item['output_blob']
    assert any(x['question_id']==q.name and x['relationship']=='produced' for x in data['questions'])
    checks.append({'artifact':item['artifact'],'output_blob':item['output_blob'],'verified':True})
reused=['artifact_1dc56cde62ec0f2c595bb2ccdb71d1259b3c4dec85cda82a2ec057ab5761b9b7','artifact_0ad2e6fbf524635e89a43ac014998f9e8664b449e102c1b47eb5322fe5145fda','artifact_37ef0bc3c27d4300181a44fba79f9ebc5be92fb5c72b2f9f506822180ab7ef72','artifact_4b385be467af9cd4992245cd4330a7a17d75a18bcc53ea37b5fc3deff41ac57c','artifact_0213c2f091660f901efa1f8f3f5946072bc0e7bd5ce97d1951b413b4ad2c8c14','artifact_e6e77f15d2a18eeb984527b35e0ced9cc096850cc48964e097afc0bdb551d5d7']
for aid in reused:
    data=cli(['artifact','show',aid])
    assert any(x['question_id']==q.name and x['relationship']=='reused' for x in data['questions'])
    checks.append({'artifact':aid,'relationship':'reused','verified':True})
(q/'outputs/publication-readback-r001.json').write_text(json.dumps(checks,indent=2,allow_nan=False))
print(json.dumps({'verified_checks':len(checks),'main_post':checks[0]['post'],'main_artifacts':len(checks[0]['artifacts'])}))
