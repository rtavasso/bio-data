"""Resume an interrupted public response into a new native file; retain the partial."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import httpx
Q=Path(__file__).resolve().parents[1]
P=Q/'inputs/public'
partial=P/'QTD000100.all.tsv.gz'
dest=P/'QTD000100.complete.all.tsv.gz'
url='https://ftp.ebi.ac.uk/pub/databases/spot/eQTL/sumstats/QTS000012/QTD000100/QTD000100.all.tsv.gz'
assert partial.exists() and not dest.exists()
rec={'url':url,'start_utc':dt.datetime.now(dt.UTC).isoformat(),
     'partial_file':str(partial.relative_to(Q)),'partial_bytes':partial.stat().st_size,
     'interruption':'terminal tool timed out after 420 seconds; initial request headers/receipt absent',
     'note':'Prefix is verified against a fresh response; resumed suffix has its own HTTP headers.'}
h=hashlib.sha256()
with partial.open('rb') as f:
    while block:=f.read(2**20): h.update(block)
rec['partial_sha256']=h.hexdigest()
with httpx.Client(timeout=180,follow_redirects=True) as c:
    r=c.get(url,headers={'Range':'bytes=0-65535','Accept-Encoding':'identity'})
    (P/'QTD000100.prefix-check.bin').write_bytes(r.content)
    rec['prefix_check']={'status':r.status_code,'headers':dict(r.headers),'sha256':hashlib.sha256(r.content).hexdigest()}
    assert r.status_code==206
    with partial.open('rb') as f: assert f.read(len(r.content))==r.content
    etag=r.headers.get('etag')
    req={'Range':f'bytes={partial.stat().st_size}-','Accept-Encoding':'identity'}
    if etag: req['If-Match']=etag
    with c.stream('GET',url,headers=req) as r:
        rec['resume']={'request_headers':req,'status':r.status_code,'headers':dict(r.headers)}
        assert r.status_code==206
        lo,hi,total=map(int,re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',r.headers['content-range']).groups())
        assert lo==partial.stat().st_size and hi==total-1
        assert shutil.disk_usage(Q).free-total>5368709120
        with dest.open('xb') as f:
            with partial.open('rb') as src: shutil.copyfileobj(src,f)
            for b in r.iter_bytes():
                assert shutil.disk_usage(Q).free-len(b)>5368709120
                f.write(b);h.update(b)
        assert dest.stat().st_size==total
rec.update(bytes=dest.stat().st_size,sha256=h.hexdigest(),status=206,transport_complete=True,
           end_utc=dt.datetime.now(dt.UTC).isoformat())
Path(str(dest)+'.receipt.json').write_text(json.dumps(rec,indent=2))
print(json.dumps(rec),flush=True)
