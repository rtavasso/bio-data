"""Fetch additional exact native tar members from a saved complete inventory."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import httpx
Q=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('pattern');a=p.parse_args()
inv=json.loads((Q/'inputs/ranges'/a.name/'inventory.json').read_text())
out=Q/'inputs/native'/a.name
with httpx.Client(timeout=240,follow_redirects=True) as client:
    for m in inv['members']:
        if not m['is_file'] or not re.search(a.pattern,m['name']): continue
        dest=out/Path(m['name']).name
        if dest.exists(): continue
        assert shutil.disk_usage(Q).free-m['bytes']>5368709120
        start=m['offset_data'];end=start+m['bytes']-1
        hdr={'Range':f'bytes={start}-{end}','If-Match':inv['etag'],'Accept-Encoding':'identity'}
        r=client.get(inv['url'],headers=hdr)
        with dest.open('xb') as f: f.write(r.content)
        rec={'url':inv['url'],'request_headers':hdr,'response_headers':dict(r.headers),'status':r.status_code,
             'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),
             'time':dt.datetime.now(dt.UTC).isoformat(),'tar_member':m}
        Path(str(dest)+'.receipt.json').write_text(json.dumps(rec,indent=2))
        assert r.status_code==206 and r.headers['content-range']==f'bytes {start}-{end}/{inv["total_bytes"]}'
        assert r.headers['etag']==inv['etag'] and len(r.content)==m['bytes']
        print(dest.name,len(r.content),flush=True)
