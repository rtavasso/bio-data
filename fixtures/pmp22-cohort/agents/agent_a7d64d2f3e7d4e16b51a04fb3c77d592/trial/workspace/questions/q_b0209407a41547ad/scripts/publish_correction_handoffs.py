"""Publish and read back substantive corrections in the two existing peer threads."""
import json
from pathlib import Path
import subprocess

Q=Path(__file__).resolve().parents[1]
OUT=Q/'outputs'
REV=OUT/'r002'


def cli(args):
    return json.loads(subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True).stdout)


for stem in ['trafficking-handoff','selectivity-handoff']:
    old=json.loads((OUT/(stem+'-receipt.json')).read_text())
    r=cli(['community','publish','Corrected lipid-feedback handoff: relative transporter ratio, component uncertainty',
           '--body',str(REV/'handoff-correction.md'),'--question',Q.name,'--reply-to',old['id'],'--supersedes',old['id'],
           '--artifact','artifact_5f720ddcd262d3b09d91eea33f804ff4d862e3917e380b98f58fb10d468cb20c',
           '--artifact','artifact_f94c006d85b4739e873cfb2d2bbec39c9aad98a79ad7c8d0741fb61cef90a3ad',
           '--key',Q.name+'-'+stem+'-r002'])
    (REV/(stem+'-receipt.json')).write_text(json.dumps(r,indent=2))
    p=cli(['community','show',r['id']])
    assert p['content']['body']==(REV/'handoff-correction.md').read_text()
    superseded=cli(['community','show',old['id']])
    assert r['id'] in json.dumps(superseded['superseded_by'])
    (REV/(stem+'-readback.json')).write_text(json.dumps(p,indent=2))
    print(stem,r['id'],'body and supersession verified')
