"""Local retrieval helper: saves actual subprocess and HTTP bytes/receipts, never executes sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone
import urllib.request
import urllib.error

Q = Path(__file__).resolve().parents[1]

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['bio', 'http', 'pretty'])
    ap.add_argument('name')
    ap.add_argument('args', nargs=argparse.REMAINDER)
    ns = ap.parse_args()
    if ns.mode == 'bio':
        run = subprocess.run(['./bin/bio', *ns.args], capture_output=True, text=True)
        target = Q / 'inputs/community' / (ns.name + '.json')
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(run.stdout)
        dump(target.with_suffix('.receipt.json'), {'command': run.args, 'exit_code': run.returncode, 'stderr': run.stderr, 'utc': datetime.now(timezone.utc).isoformat()})
        if run.returncode:
            print(run.stderr)
            raise SystemExit(run.returncode)
        d = json.loads(run.stdout)
        if isinstance(d, dict) and 'items' in d:
            print(json.dumps({'total': d.get('total'), 'next_offset': d.get('next_offset'), 'items': [{'subject': x.get('subject'), 'title': x.get('title'), 'superseded_by': x.get('superseded_by')} for x in d['items']]}, indent=2))
        elif isinstance(d, dict) and 'manifest' in d:
            print(json.dumps({k: v for k, v in d.items() if k != 'manifest'}, indent=2))
        else:
            print(json.dumps(d, indent=2))
    elif ns.mode == 'http':
        target = Q / 'inputs/public' / ns.name
        if target.exists():
            raise FileExistsError(target)
        url = ns.args[0]
        receipt = {'url': url, 'utc': datetime.now(timezone.utc).isoformat()}
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'PMP22-human-dosage-research/1.0'})
            with urllib.request.urlopen(req, timeout=90) as r:
                payload = r.read()
                receipt.update(status=r.status, final_url=r.url, content_type=r.headers.get('Content-Type'))
        except urllib.error.HTTPError as e:
            payload = e.read()
            receipt.update(status=e.code, error=str(e))
        except Exception as e:
            payload = b''
            receipt.update(status=None, error=str(e))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        receipt.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), path=str(target))
        dump(target.with_name(target.name + '.receipt.json'), receipt)
        print(json.dumps(receipt, indent=2))
    else:
        target = Q / 'inputs' / ns.name
        d = json.loads(Path(os.path.expandvars(ns.args[0])).read_text())
        dump(target, d)
        print(target)

if __name__ == '__main__':
    main()
