import json, subprocess
from pathlib import Path
P=Path(__file__).resolve().parents[1]
pub=json.loads((P/'outputs/peer-publication.json').read_text())
r=subprocess.run(['./bin/bio','community','show',pub['id']],capture_output=True,text=True,check=True)
(P/'outputs/peer-readback.json').write_text(r.stdout)
d=json.loads(r.stdout)
assert d['content']['body']==(P/'peer-response.md').read_text()
assert d['parent']=='post_10b061c155e74f9d9e71adc901c2721f'
print('VERIFIED_PEER_REPLY',d['id'])
main=json.loads((P/'outputs/publication-readback.json').read_text())
products=json.loads((P/'outputs/registered-products.json').read_text())
assert set(main['content']['evidence']['artifacts'])=={x['artifact'] for x in products}
work=json.loads((P/'outputs/work-completed-readback.json').read_text())
assert work['status']=='completed'
print('VERIFIED_MAIN_POST',main['id'],'ARTIFACTS',len(products),'STATUS',work['status'])
