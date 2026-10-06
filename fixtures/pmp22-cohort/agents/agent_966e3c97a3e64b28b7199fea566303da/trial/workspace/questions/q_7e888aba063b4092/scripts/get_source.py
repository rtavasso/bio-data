"""Explicit source transport with per-attempt receipts and configured disk reserve."""
import datetime
import hashlib
import json
import os
import shutil
import sys
import time
import tomllib
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'inputs'/'sources'
DEST.mkdir(parents=True,exist_ok=True)
config = tomllib.loads((Path(os.environ['BIO_WORKSPACE'])/'config.toml').read_text())['budgets']
name,url = sys.argv[1:3]
path = DEST/name
stamp = str(time.time_ns())
receipt = {'url':url,'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'GET','path':str(path),'receipt_kind':'actual HTTP attempt'}
assert not path.exists(), f'Preserve existing source: {path}'
try:
    disk = shutil.disk_usage(DEST)
    reserve = max(config['reserve_bytes'],int(config['reserve_fraction']*disk.total))
    assert disk.free > reserve
    with httpx.Client(timeout=120,follow_redirects=True) as client:
        with client.stream('GET',url,headers={'User-Agent':'bio-data research source audit'}) as response:
            receipt.update(status=response.status_code,final_url=str(response.url),content_type=response.headers.get('content-type'),content_length=response.headers.get('content-length'))
            size = 0
            with path.open('xb') as f:
                for chunk in response.iter_bytes():
                    assert shutil.disk_usage(DEST).free-len(chunk) > reserve
                    f.write(chunk)
                    size += len(chunk)
            receipt.update(bytes=size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),http_success=response.is_success)
except Exception as exc:
    receipt['error']=repr(exc)
finally:
    receipt['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (DEST/(name+'.'+stamp+'.receipt.json')).write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
print(json.dumps(receipt,indent=2))
