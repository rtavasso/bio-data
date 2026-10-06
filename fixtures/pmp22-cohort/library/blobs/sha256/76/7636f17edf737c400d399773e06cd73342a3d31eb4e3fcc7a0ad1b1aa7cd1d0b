"""Preserve an exact public response with an exclusive per-attempt receipt; TLS stays on."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import requests

Q = Path(__file__).resolve().parents[1]
I = Q / 'inputs' / 'public'
I.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('name')
parser.add_argument('url')
args = parser.parse_args()
path = I / args.name
receipt_path = I / (args.name + '.receipt.json')
assert not path.exists() and not receipt_path.exists(), 'Use a fresh attempt name'
r = dict(name=args.name, url=args.url, started=datetime.datetime.now(datetime.timezone.utc).isoformat(), bytes=0, status='failed', sha256=None, request_count=1)
try:
    with requests.get(args.url, timeout=(30, 180), stream=True, verify=os.environ.get('SSL_CERT_FILE', True)) as response:
        r.update(http_status=response.status_code, final_url=response.url, headers=dict(response.headers), redirects=[dict(url=x.url, status=x.status_code) for x in response.history], request_count=1+len(response.history))
        with path.open('xb') as out:
            for b in response.iter_content(1024*1024):
                out.write(b)
                r['bytes'] += len(b)
        r['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        response.raise_for_status()
        r['status'] = 'downloaded_not_yet_scientifically_validated'
except Exception as error:
    r['error'] = repr(error)
    if path.exists():
        r['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
r['finished'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
if path.exists():
    p = subprocess.run(['./bin/bio', 'object', 'add', str(path), '--classification', 'source'], capture_output=True, text=True)
    r['object_receipt'] = json.loads(p.stdout) if p.returncode == 0 else dict(error=p.stderr)
receipt_path.write_text(json.dumps(r, indent=2, allow_nan=False) + '\n')
print(json.dumps(r, indent=2))
raise SystemExit(0 if r['status'] != 'failed' else 1)
