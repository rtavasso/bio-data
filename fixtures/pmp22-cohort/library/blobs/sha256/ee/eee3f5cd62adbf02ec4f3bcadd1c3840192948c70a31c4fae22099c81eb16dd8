"""Acquire exact public bytes, preserve success/failure receipts; no raw processing."""
import concurrent.futures
import datetime
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'inputs' / 'public'
DEST.mkdir(parents=True, exist_ok=True)

def fetch(spec):
    name, url = spec.split('=', 1)
    path = DEST / name
    receipt = DEST / (name + '.receipt.json')
    if path.exists() or receipt.exists():
        raise ValueError('Refusing to overwrite source/receipt: ' + name)
    rec = {'url': url, 'retrieved_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'method': 'GET', 'transport': 'urllib.request', 'name': name}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'bio-data-research-source-audit/1.0'})
        with urllib.request.urlopen(req, timeout=90) as res:
            body = res.read(30_000_001)
            if len(body) > 30_000_000:
                raise ValueError('Selected metadata/processed source exceeds 30 MB guard; inspect before acquisition')
            rec.update(status=res.status, final_url=res.url, content_type=res.headers.get('Content-Type'))
    except urllib.error.HTTPError as err:
        body = err.read()
        rec.update(status=err.code, error=str(err), final_url=err.url)
    except Exception as err:
        body = b''
        rec.update(status=None, error=repr(err))
    rec.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), success=rec.get('status') == 200)
    if body:
        path.write_bytes(body)
        path.chmod(0o444)
    receipt.write_text(json.dumps(rec, indent=2, allow_nan=False) + '\n')
    print(json.dumps(rec), flush=True)
    return rec

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    rows = list(pool.map(fetch, sys.argv[1:]))
if not all(r['success'] for r in rows):
    sys.exit(1)
