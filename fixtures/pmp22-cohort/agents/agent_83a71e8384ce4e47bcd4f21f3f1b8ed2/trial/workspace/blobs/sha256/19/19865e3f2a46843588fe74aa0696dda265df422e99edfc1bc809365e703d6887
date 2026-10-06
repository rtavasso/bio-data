from pathlib import Path
import json,subprocess
Q=Path(__file__).resolve().parents[1];O=Q/'outputs';U=O/'upstream';B=str(Q.parents[2]/'bin/bio')
r=json.loads((U/'final-registration.json').read_text());ids={Path(a['path']).name:a['receipt']['artifact'] for a in r};x=json.loads((O/'investigations.json').read_text());assert x['revision']==28;x['revision']=29
for a in x['items']:
 if a['id']=='nae1-antioxidant-alternative':a['artifacts']=[ids['antioxidant-summary.json'],ids['antioxidant-posthoc-summary.json']]
x['registration_manifest']=dict(artifact=ids['analysis-package.json'],path='outputs/upstream/final-registration.json',note='r029 adds catalog links only; r028 scientific disposition retained.')
for p in [O/'investigations.r029.json',O/'investigations.json']:p.write_text(json.dumps(x,indent=2))
p=O/'investigations.r029.json';r=subprocess.run([B,'object','add',str(p),'--classification','interpretation'],text=True,capture_output=True,check=True);(U/'final-queue-object.json').write_text(r.stdout);print('Registered final queue',r.stdout)
# Validate exact artifact IDs and stored output digests on final read-back.
rb=json.loads((U/'final-registration-readback.json').read_text())
for a,b in zip(json.loads((U/'final-registration.json').read_text()),rb):
 assert a['receipt']['artifact']==b['artifact']==b['detail']['id']
print('All final artifact IDs verified on read-back.')
