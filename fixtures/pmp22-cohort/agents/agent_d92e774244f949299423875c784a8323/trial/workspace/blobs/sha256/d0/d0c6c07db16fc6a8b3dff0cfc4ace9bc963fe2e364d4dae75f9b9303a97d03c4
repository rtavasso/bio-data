"""Fetch and inspect a tabix-indexed BGZF genomic interval with preserved HTTP ranges.
Only numeric index offsets are consumed; no source code or serialized objects execute.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
from pathlib import Path
import struct
import httpx
Q=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('dataset');p.add_argument('study');p.add_argument('position',type=int)
p.add_argument('--flavor',choices=['all','cc'],default='all')
a=p.parse_args();pos0=a.position-1
base=f'https://ftp.ebi.ac.uk/pub/databases/spot/eQTL/sumstats/{a.study}/{a.dataset}/{a.dataset}.{a.flavor}.tsv.gz'
out=Q/'inputs/ranges'/f'{a.dataset}-{a.position}-{a.flavor}';out.mkdir(parents=True,exist_ok=False)
c=httpx.Client(timeout=180,follow_redirects=True)
requests=[]
def get(url,name,headers=None):
    r=c.get(url,headers=headers)
    path=out/name;path.write_bytes(r.content)
    rec={'url':url,'request_headers':headers or {},'status':r.status_code,'response_headers':dict(r.headers),
         'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'time':dt.datetime.now(dt.UTC).isoformat()}
    Path(str(path)+'.receipt.json').write_text(json.dumps(rec,indent=2))
    requests.append(rec)
    assert r.status_code==(206 if headers else 200)
    return r
r=get(base+'.tbi','index.tbi');idx=io.BytesIO(gzip.decompress(r.content))
assert idx.read(4)==b'TBI\1'
n_ref,fmt,seq_col,beg_col,end_col,meta,skip,l_names=struct.unpack('<8i',idx.read(32))
names=idx.read(l_names).rstrip(b'\0').decode().split('\0')
assert len(names)==n_ref
index={}
for name in names:
    nb=struct.unpack('<i',idx.read(4))[0];bins={}
    for _ in range(nb):
        b,n=struct.unpack('<Ii',idx.read(8))
        bins[b]=[struct.unpack('<QQ',idx.read(16)) for _ in range(n)]
    ni=struct.unpack('<i',idx.read(4))[0]
    lin=[struct.unpack('<Q',idx.read(8))[0] for _ in range(ni)]
    index[name]=(bins,lin)
chrom='17' if '17' in index else 'chr17';bins,lin=index[chrom]
# Standard reg2bins for the zero-based half-open single-base interval.
want={0}
for shift,basebin in [(26,1),(23,9),(20,73),(17,585),(14,4681)]:want.add(basebin+(pos0>>shift))
minoff=lin[min(pos0>>14,len(lin)-1)] if lin else 0
chunks=sorted({(s,e) for b in want for s,e in bins.get(b,[]) if e>minoff})
merged=[]
for s,e in chunks:
    if merged and s<=merged[-1][1]:merged[-1][1]=max(e,merged[-1][1])
    else:merged.append([s,e])

def blocks(data):
    start=0
    while start+18<=len(data):
        assert data[start:start+3]==b'\x1f\x8b\x08'
        xlen=struct.unpack_from('<H',data,start+10)[0]
        off=start+12;stop=off+xlen;size=None
        while off<stop:
            key=data[off:off+2];ln=struct.unpack_from('<H',data,off+2)[0]
            if key==b'BC':size=struct.unpack_from('<H',data,off+4)[0]+1
            off+=4+ln
        assert size is not None
        if start+size>len(data):break
        yield start,gzip.decompress(data[start:start+size])
        start+=size

r=get(base,'header.bgzf',{'Range':'bytes=0-65535','Accept-Encoding':'identity'})
etag=r.headers.get('etag');total=int(r.headers['content-range'].split('/')[-1])
header=b''.join(b for _,b in blocks(r.content)).splitlines()[0].decode()
columns=header.lstrip('#').split('\t');records=[]
for j,(s,e) in enumerate(merged):
    lo=s>>16;hi=min((e>>16)+65535,total-1)
    h={'Range':f'bytes={lo}-{hi}','Accept-Encoding':'identity'}
    if etag:h['If-Match']=etag
    r=get(base,f'chunk-{j:03d}.bgzf',h)
    assert r.headers['content-range']==f'bytes {lo}-{hi}/{total}'
    if etag:assert r.headers.get('etag')==etag
    pieces=[]
    for off,data in blocks(r.content):
        absblock=lo+off
        if absblock<(s>>16) or absblock>(e>>16):continue
        l=(s&65535) if absblock==(s>>16) else 0
        rr=(e&65535) if absblock==(e>>16) else len(data)
        pieces.append(data[l:rr])
    lines=b''.join(pieces).decode().splitlines()
    for i,line in enumerate(lines):
        vals=line.split('\t')
        assert len(vals)==len(columns),(len(vals),len(columns),line[:100])
        if vals[seq_col-1]==chrom and int(vals[beg_col-1])==a.position:
            records.append(dict(zip(columns,vals),range_chunk=j,chunk_line=i+1))
# A record may be returned by more than one overlap chunk; assert dedup on complete source fields.
unique={tuple(r[k] for k in columns):r for r in records}
result={'dataset':a.dataset,'position1':a.position,'chromosome':chrom,'index_format':fmt,
        'seq_col':seq_col,'beg_col':beg_col,'end_col':end_col,'header':columns,'chunks':merged,
        'records':list(unique.values()),'raw_matching_rows':len(records),'unique_rows':len(unique),
        'note':'All source rows at the requested variant position, not all gene or chromosome variants. Each HTTP range retained.'}
(out/'result.json').write_text(json.dumps(result,indent=2))
print('RESULT',a.dataset,'position',a.position,'rows',len(unique),'columns',columns)
for x in result['records']:
    if any('ENSG00000109099' in v or '15260761' in v or '15265154' in v for k,v in x.items() if isinstance(v,str)):
        print('PMP22 TARGET',x)
c.close()
