"""Retrieve explicit public URLs and preserve actual transport receipts and source bytes."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'inputs/public'
OUT.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('name')
parser.add_argument('url')
args = parser.parse_args()
assert Path(args.name).name == args.name
path = OUT / args.name
receipt_path = OUT / (args.name + '.receipt.json')
assert not path.exists() and not receipt_path.exists(), 'Do not overwrite an acquisition; use a new version.'
reserve = 5368709120
assert shutil.disk_usage(OUT).free > reserve
receipt = {'url': args.url, 'started': datetime.now(timezone.utc).isoformat(), 'body': str(path), 'status': None}
try:
    with httpx.stream('GET', args.url, follow_redirects=True, timeout=120) as response:
        receipt.update({'status': response.status_code, 'final_url': str(response.url), 'headers': {k: v for k, v in response.headers.items() if k.lower() in {'content-type', 'content-length', 'last-modified', 'etag'}}})
        h = hashlib.sha256()
        size = 0
        with path.open('xb') as stream:
            for chunk in response.iter_bytes():
                assert shutil.disk_usage(OUT).free - len(chunk) > reserve, 'Configured disk reserve reached.'
                stream.write(chunk)
                h.update(chunk)
                size += len(chunk)
        receipt.update({'bytes': size, 'sha256': h.hexdigest(), 'complete_body': True})
except Exception as exc:
    receipt['error'] = repr(exc)
finally:
    receipt['finished'] = datetime.now(timezone.utc).isoformat()
    receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False))
print(json.dumps(receipt, indent=2))
if receipt.get('error') or receipt['status'] != 200:
    raise SystemExit(1)
