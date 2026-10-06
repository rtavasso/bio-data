"""Question-local read-only discovery and source transport with saved receipts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

Q = Path(__file__).resolve().parents[1]
IN = Q / 'inputs'
OUT = Q / 'outputs'
IN.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)


def cli(args, label):
    p = subprocess.run(['./bin/bio', *args], capture_output=True, text=True)
    (OUT / f'{label}.json').write_text(p.stdout)
    if p.returncode:
        print(p.stderr)
        raise RuntimeError((args, p.returncode))
    return json.loads(p.stdout)


mode = sys.argv[1]
if mode == 'forum':
    for term in sys.argv[2:]:
        doc = cli(['community', 'search', '--text', term, '--limit', '40'], 'forum-' + term.replace(' ', '_'))
        print(term, 'total', doc['total'], 'next', doc['next_offset'])
        for x in doc['items']:
            print(x['subject'], x['title'], x['summary'][:450], 'superseded', x['superseded_by'])
elif mode == 'show':
    for post in sys.argv[2:]:
        doc = cli(['community', 'show', post], post)
        print(post, doc['content']['title'], doc['content']['body'])
        print('EVIDENCE', json.dumps(doc['content'].get('evidence')), 'REPLIES', doc.get('replies'), 'SUPERSEDED', doc.get('superseded_by'))
elif mode == 'artifact':
    for aid in sys.argv[2:]:
        doc = cli(['artifact', 'show', aid], aid)
        print(json.dumps(doc, indent=2))
elif mode == 'search':
    for term in sys.argv[2:]:
        for family in ['data', 'artifact', 'work']:
            doc = cli([family, 'search', '--text', term], family + '-' + term.replace(' ', '_'))
            print(family, term, json.dumps(doc)[:12000])
elif mode == 'http':
    name, url = sys.argv[2:]
    target = IN / name
    assert not target.exists(), target
    receipt = {'url': url, 'started': datetime.now(timezone.utc).isoformat(), 'inherited': False}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'bio-data-research/1.0'})
        with urllib.request.urlopen(req, timeout=90) as response:
            body = response.read()
            receipt.update(status=response.status, final_url=response.url, content_type=response.headers.get('Content-Type'))
    except urllib.error.HTTPError as e:
        body = e.read()
        receipt.update(status=e.code, error=str(e))
    except Exception as e:
        body = b''
        receipt.update(status=None, error=repr(e))
    target.write_bytes(body)
    receipt.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), finished=datetime.now(timezone.utc).isoformat())
    target.with_name(target.name + '.receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))
else:
    raise ValueError(mode)
