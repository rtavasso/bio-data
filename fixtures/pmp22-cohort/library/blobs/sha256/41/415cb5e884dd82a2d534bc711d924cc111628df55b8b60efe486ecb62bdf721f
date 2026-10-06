"""Record current peer discovery before choosing public measurements."""
import json
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]
o=q/'inputs/community'
o.mkdir(parents=True,exist_ok=True)

def cli(args,label):
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True)
    (o/(label+'.json')).write_text(p.stdout)
    if p.returncode:
        (o/(label+'.stderr')).write_text(p.stderr)
        print(p.stderr)
        p.check_returncode()
    return json.loads(p.stdout)

posts={}
for i,text in enumerate(['PMP22','RBP','RNA binding','HNRNP','IGF2BP','G3BP','GSE118660','ENCSR456FVU','K562','HepG2']):
    result=cli(['community','search','--text',text,'--limit','100'],f'search-{i:02}')
    assert result.get('next_offset') is None, 'Paginate before claiming completeness'
    for item in result['items']:
        posts[item['subject']]=item['title']
    print(text, result['total'])
for post in ['post_1b2c4f75fb614dd7931820b681db11d7','post_f8fc24f8e60e440c8456ebe336849908','post_d6a2ae5d24b64dd9a5069f793e51e049']:
    r=cli(['community','show',post],post)
    print('READ',post,r['content']['title'])
    for child in r.get('replies',[]):
        childpost=cli(['community','show',child['id']],child['id'])
        print('REPLY',child['id'],childpost['content']['title'])
cli(['community','agents'],'agents')
for kind in ['artifact','work','data']:
    for text in ['RBP','ENCODE','Schwann']:
        result=cli(['--workspace',str(Path(__import__('os').environ['BIO_COMMUNITY'])/'library'),kind,'search','--text',text],f'library-{kind}-{text}')
        print('LIBRARY',kind,text, result.get('total'))
(o/'post-index.json').write_text(json.dumps(posts,indent=2))
print(json.dumps(posts,indent=2))
