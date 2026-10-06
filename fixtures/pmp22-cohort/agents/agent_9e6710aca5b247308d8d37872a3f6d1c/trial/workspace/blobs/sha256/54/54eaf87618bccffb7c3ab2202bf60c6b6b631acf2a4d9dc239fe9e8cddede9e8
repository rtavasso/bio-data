"""Acquire selected processed assets only, retaining CLI receipts and hashes."""
import gzip,hashlib,json,subprocess
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
D=Q/'inputs/acquisition';D.mkdir(parents=True,exist_ok=True)
WORK=Q.parents[1]

def bio(*args):
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

bundles={'GSE79115':'bundle_a7928e2ca404ba58cb76b6f9','GSE94990':'bundle_d129282c498839cbda2fcba4','GSE98547':'bundle_2fcbac7648468e7be3c94e3d','GSE292211':'bundle_2513810f0d1228c98191ea93'}
manifest=[]
for series,bundle in bundles.items():
    listing=bio('data','list','--scope',bundle,'--limit','100')
    (D/(series+'-inventory.json')).write_text(json.dumps(listing,indent=2)+'\n')
    assert listing['next_offset'] is None
    for item in listing['items']:
        name=item['name']
        eligible=name.endswith('.txt.gz') or (series=='GSE94990' and any(f'GSM{x}_' in name for x in range(2493836,2493842)))
        if not eligible: continue
        rp=D/(name+'.fetch.json')
        if rp.exists(): r=json.loads(rp.read_text())
        else:
            r=bio('fetch',item['asset_revision'],'--question','q_4f573ee10eee421b')
            rp.write_text(json.dumps(r,indent=2)+'\n')
        assert r['outcome']=='available_full',r
        path=WORK/'blobs/sha256'/r['blob'][:2]/r['blob']
        with path.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==r['blob']
        with gzip.open(path,'rt') as f:
            header=[f.readline().rstrip('\n') for _ in range(4)]
        manifest.append({'series':series,'name':name,**r,'path':str(path.relative_to(WORK)),'first_lines':header})
        (D/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
        print(series,name,r['blob'],path.stat().st_size,header[:2])
