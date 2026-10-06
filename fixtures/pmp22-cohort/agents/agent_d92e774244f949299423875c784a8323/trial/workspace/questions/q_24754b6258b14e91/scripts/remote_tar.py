"""Read a remote uncompressed tar using validated HTTP ranges; preserve exact bytes."""
import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
import httpx

Q=Path(__file__).resolve().parents[1]

class Remote(io.RawIOBase):
    def __init__(self,url,out):
        self.url=url
        self.out=out
        self.pos=0
        self.total=None
        self.etag=None
        self.n=0
        self.client=httpx.Client(timeout=180,follow_redirects=True)
        self.responses=[]
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self,n,whence=0):
        if whence==0: self.pos=n
        elif whence==1: self.pos+=n
        else: self.pos=self.total+n
        return self.pos
    def read(self,n=-1):
        if n==0: return b''
        assert n>0
        if self.total is not None and self.pos>=self.total: return b''
        end=self.pos+n-1
        if self.total is not None: end=min(end,self.total-1)
        req={'Range':f'bytes={self.pos}-{end}','Accept-Encoding':'identity'}
        if self.etag: req['If-Match']=self.etag
        r=self.client.get(self.url,headers=req)
        self.n+=1
        dest=self.out/f'range-{self.n:05d}.bin'
        dest.write_bytes(r.content)
        rec={'url':self.url,'range':req['Range'],'status':r.status_code,'headers':dict(r.headers),
             'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),
             'file':str(dest.relative_to(Q)),'time':dt.datetime.now(dt.UTC).isoformat()}
        (self.out/f'range-{self.n:05d}.receipt.json').write_text(json.dumps(rec,indent=2))
        self.responses.append(rec)
        assert r.status_code==206,(r.status_code,r.text[:100])
        a,b,total=map(int,re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',r.headers['content-range']).groups())
        assert a==self.pos and b==end and len(r.content)==b-a+1
        if self.total is not None: assert self.total==total
        self.total=total
        if self.etag: assert self.etag==r.headers['etag']
        self.etag=r.headers['etag']
        self.pos+=len(r.content)
        return r.content

p=argparse.ArgumentParser()
p.add_argument('name');p.add_argument('url');p.add_argument('--select',required=True)
a=p.parse_args()
out=Q/'inputs/ranges'/a.name
out.mkdir(parents=True,exist_ok=False)
native=Q/'inputs/native'/a.name
native.mkdir(parents=True,exist_ok=False)
r=Remote(a.url,out)
inventory=[]
try:
    with tarfile.open(fileobj=r,mode='r:') as tar:
        for m in tar:
            entry={'name':m.name,'bytes':m.size,'offset':m.offset,'offset_data':m.offset_data,'is_file':m.isfile()}
            if m.isfile() and re.search(a.select,m.name):
                assert shutil.disk_usage(Q).free-2*m.size>5368709120
                data=tar.extractfile(m).read()
                dest=native/Path(m.name).name
                with dest.open('xb') as f: f.write(data)
                entry.update(selected_path=str(dest.relative_to(Q)),sha256=hashlib.sha256(data).hexdigest())
                print('SELECTED',m.name,m.size,flush=True)
            inventory.append(entry)
    result={'url':a.url,'total_bytes':r.total,'etag':r.etag,'select_regex':a.select,'complete_inventory':True,
            'members':inventory,'requests':len(r.responses)}
    (out/'inventory.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print('DONE',a.name,len(inventory),len(r.responses))
finally:
    r.client.close()
