"""Bounded, explicit HTTP transport with immutable payloads and per-attempt receipts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from threading import Lock
import time
import tomllib
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit, parse_qs

q=Path(__file__).resolve().parents[1]
w=Path(os.environ['BIO_WORKSPACE'])
config=tomllib.loads((w/'config.toml').read_text())
STORE_LOCK=Lock()


def retrieve(label,url):
    out=q/'inputs/http'
    out.mkdir(parents=True,exist_ok=True)
    rp=out/(label+'.receipt.json')
    assert not rp.exists(), 'New actual attempt requires a fresh label'
    rec={'url':url,'started_utc':datetime.now(timezone.utc).isoformat(),'label':label,
         'method':'GET','tls_verification':True,'producer':str(Path(__file__).relative_to(q)),
         'producer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    p=out/(label+'.payload')
    start=time.monotonic()
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'bio-data-research/1.0','Accept':'application/json, application/xml, text/html, */*'})
        try:
            response=urllib.request.urlopen(req,timeout=120)
        except urllib.error.HTTPError as exc:
            response=exc
        with response:
            parts=urlsplit(response.url)
            query_keys=set(parse_qs(parts.query))
            signed=bool(query_keys.intersection({'Signature','AWSAccessKeyId','x-amz-security-token','X-Amz-Signature','X-Amz-Credential'}))
            final=urlunsplit((parts.scheme,parts.netloc,parts.path,'SIGNED_QUERY_REDACTED' if signed else parts.query,parts.fragment))
            rec.update(status=response.status,final_url=final,
                       content_type=response.headers.get('Content-Type'),content_length=response.headers.get('Content-Length'))
            n=0
            with p.open('xb') as dest:
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:
                        break
                    disk=shutil.disk_usage(w)
                    budget=config.get('budgets',{})
                    reserve=max(budget.get('reserve_bytes',5*2**30),int(disk.total*budget.get('reserve_fraction',0)))
                    if disk.free-len(chunk)<reserve:
                        raise RuntimeError('Configured disk reserve would be crossed')
                    dest.write(chunk)
                    n+=len(chunk)
            rec.update(bytes=n,complete=True,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            if rec['content_length'] and rec['content_length'].isdigit():
                assert n==int(rec['content_length']), 'Length mismatch'
        with STORE_LOCK:
            added=subprocess.run(['./bin/bio','object','add',str(p)],capture_output=True,text=True)
        if added.returncode:
            rec['storage_error']=added.stderr
        else:
            rec['object']=json.loads(added.stdout)
    except Exception as exc:
        rec.update(error=repr(exc),complete=False)
        if p.exists():
            rec.update(partial_bytes=p.stat().st_size,partial_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    rec['elapsed_seconds']=time.monotonic()-start
    rp.write_text(json.dumps(rec,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in rec.items() if k!='object'},allow_nan=False),flush=True)
    return rec

if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('label')
    a.add_argument('url')
    args=a.parse_args()
    retrieve(args.label,args.url)
