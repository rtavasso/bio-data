"""Question-local immutable source retrieval/inspection, no downloaded code execution."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import textwrap
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]

def sha(b):
    return hashlib.sha256(b).hexdigest()

def blob(h):
    for base in [W, Path(os.environ['BIO_COMMUNITY']) / 'library']:
        p = base / 'blobs/sha256' / h[:2] / h
        if p.exists():
            b = p.read_bytes()
            assert sha(b) == h
            return b
    raise FileNotFoundError(h)

def render(p):
    b = p.read_bytes()
    dest = Q / 'outputs' / (p.stem + '-source.txt')
    if p.suffix == '.xml':
        root = ET.fromstring(b)
        lines = []
        for n, elem in enumerate(root.iter()):
            if elem.tag in ('p', 'title', 'article-title', 'caption', 'ref', 'table-wrap'):
                text = ' '.join(''.join(elem.itertext()).split())
                lines.append(f'[{n}] {elem.tag} id={elem.get("id", "")}\n' + textwrap.fill(text, 120))
        dest.write_text('\n\n'.join(lines))
    elif p.suffix == '.json':
        dest.write_text(json.dumps(json.loads(b), indent=2, ensure_ascii=False))
    print('RENDER', dest.name)

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['fetch', 'reuse', 'render'])
parser.add_argument('args', nargs='+')
a = parser.parse_args()
(Q / 'inputs').mkdir(exist_ok=True)
if a.mode == 'reuse':
    for pair in a.args:
        h, name = pair.split(':', 1)
        p = Q / 'inputs' / name
        b = blob(h)
        if p.exists():
            assert p.read_bytes() == b
        else:
            p.write_bytes(b)
        print('INHERITED', name, h, len(b))
        render(p)
elif a.mode == 'render':
    for name in a.args:
        render(Q / 'inputs' / name)
else:
    for jobfile in a.args:
        for job in json.loads(Path(jobfile).read_text()):
            p = Q / 'inputs' / job['name']
            receipt_path = p.with_name(p.name + '.receipt.json')
            if p.exists() or receipt_path.exists():
                raise FileExistsError(str(p))
            r = dict(job, requested_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), retrieval_agent='agent_ba1e8b55a6c142128b90ae17e6f6920d')
            try:
                req = urllib.request.Request(job['url'], headers={'User-Agent': 'PMP22-source-audit/1.0'})
                with urllib.request.urlopen(req, timeout=60) as res:
                    b = res.read()
                    r.update(status=res.status, final_url=res.url, content_type=res.headers.get('Content-Type'), bytes=len(b), sha256=sha(b))
                    p.write_bytes(b)
            except urllib.error.HTTPError as e:
                b = e.read()
                p.write_bytes(b)
                r.update(status=e.code, final_url=e.url, error=str(e), bytes=len(b), sha256=sha(b))
            except Exception as e:
                r.update(status=None, error=f'{type(e).__name__}: {e}')
            receipt_path.write_text(json.dumps(r, indent=2, allow_nan=False))
            print(json.dumps(r))
            if r.get('status') == 200 and p.suffix in ('.xml', '.json'):
                try:
                    render(p)
                except Exception as e:
                    print('INSPECTION FAILURE', type(e).__name__, str(e))
