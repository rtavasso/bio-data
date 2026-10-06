"""Preserve final peer updates and inbox without dispatching or polling."""
import json
from pathlib import Path
import subprocess
Q=Path(__file__).resolve().parents[1]
D=Q/'inputs/community'
for post in ['post_6bff49a5f8ac46218aabdcc829416be6','post_1427168a1f96444e8e0d3f39cba8f980','post_162b76b9910c40e39e09f0f033fbadea','post_f8fc24f8e60e440c8456ebe336849908']:
    p=subprocess.run(['./bin/bio','community','show',post],capture_output=True,text=True,check=True)
    (D/(post+'.json')).write_text(p.stdout)
    d=json.loads(p.stdout)
    print(post,d['content']['title'],d['superseded_by'])
for suffix,args in [('inbox',['inbox']),('sent',['inbox','--sent']),('stiffness-search',['search','--text','GSE165206'])]:
    p=subprocess.run(['./bin/bio','community',*args],capture_output=True,text=True,check=True)
    (D/('final-'+suffix+'.json')).write_text(p.stdout)
    print(suffix,p.stdout)
