"""Snapshot final community evidence once; no waiting or service dispatch."""
import json
import subprocess
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
D=Q/'inputs/community'
for p in ['post_b836db3d003d4b0b8bc5c5466a02bfbd','post_758a20acd0dd4836bec402c9a191a3ec','post_ecc13cabecf54b789e538f695e4bdca2','post_2380b4bbde9a4d218e38d4a6dfe9670f']:
    raw=subprocess.run(['./bin/bio','community','show',p],capture_output=True,text=True,check=True).stdout
    d=json.loads(raw)
    (D/(p+'-final.json')).write_text(json.dumps(d,indent=2)+'\n')
    print(p,'replies',len(d['replies']),'superseded',d.get('superseded_by'))
for key,args in [('inbox',['inbox']),('sent',['inbox','--sent']),('ENCODE',['search','--text','ENCODE','--limit','100']),('mechanics',['search','--text','mechanics','--limit','100']),('GSE79115',['search','--text','GSE79115','--limit','100']),('upstream',['search','--text','regulator activity','--limit','100'])]:
    raw=subprocess.run(['./bin/bio','community',*args],capture_output=True,text=True,check=True).stdout
    d=json.loads(raw)
    (D/('final-'+key+'.json')).write_text(json.dumps(d,indent=2)+'\n')
    if isinstance(d,dict):
        print(key,'total',d['total'],'next',d['next_offset'])
        for p in d['items']:
            print(p['subject'],p['title'])
    else:
        print(key,len(d))
