"""Find native primary texts in a published manifest; fetch missing XML with receipts."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

Q = Path(__file__).resolve().parents[1]
IN = Q / 'inputs' / 'primary'
IN.mkdir(parents=True, exist_ok=True)
LIB = Path(os.environ['BIO_COMMUNITY']) / 'library' / 'blobs' / 'sha256'
ids = ['PMC2713384', 'PMC6920087', 'PMC2728407', 'PMC3866477']
manifest_hash = '23f94e75dab1ce2b57cda1ca09d1552867e8608357dd04e88572f0bcdbe907bf'
manifest = json.loads((LIB / manifest_hash[:2] / manifest_hash).read_text())
found = {}
for h in manifest['blobs']:
    p = LIB / h[:2] / h
    if p.stat().st_size > 2000000:
        continue
    b = p.read_bytes()
    if not (b.lstrip().startswith(b'<?xml') or b.lstrip().startswith(b'<article') or b.lstrip().lower().startswith(b'<!doctype html')):
        continue
    for id_ in ids:
        if id_.encode() in b[:20000]:
            found.setdefault(id_, []).append(h)
print('SAVED PRIMARY CANDIDATES', json.dumps(found))
ledger = []
for id_ in ids:
    local = IN / (id_ + '.xml')
    if local.exists():
        print('Already acquired', id_)
        continue
    # The library candidates, if any, are retained as evidence for manual review.
    for h in found.get(id_, []):
        b = (LIB / h[:2] / h).read_bytes()
        (IN / (id_ + '-shared-' + h[:8] + '.source')).write_bytes(b)
    url = f'https://www.ebi.ac.uk/europepmc/webservices/rest/{id_}/fullTextXML'
    row = {'source': id_, 'url': url, 'utc': datetime.now(timezone.utc).isoformat(), 'library_candidates': found.get(id_, [])}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'bio-data-research/1.0'}), timeout=60) as response:
            b = response.read()
            row.update(status=response.status, final_url=response.url, content_type=response.headers.get('Content-Type'))
        local.write_bytes(b)
        row.update(bytes=len(b), sha256=hashlib.sha256(b).hexdigest(), local_path=str(local.relative_to(Q)))
        root = ET.fromstring(b)
        assert root.tag == 'article'
        row['article_ids'] = [(e.get('pub-id-type'), e.text) for e in root.findall('.//article-id')]
        # Produce a readable paragraph view with exact section/figure/table IDs, not an LLM summary.
        parts = []
        for node in root.iter():
            if node.tag in ('article-title', 'title', 'p', 'table-wrap', 'fig'):
                text = ' '.join(''.join(node.itertext()).split())
                if text:
                    parts.append(f'[{node.tag} {node.get("id", "")}] {text}')
        (IN / (id_ + '.txt')).write_text('\n\n'.join(parts))
        receipt = subprocess.run(['./bin/bio', 'object', 'add', str(local)], capture_output=True, text=True, check=True)
        row['object'] = json.loads(receipt.stdout)
        print(id_, row['article_ids'], len(b))
    except Exception as exc:
        row['error'] = repr(exc)
        print('FAIL', id_, repr(exc))
    ledger.append(row)
(IN / 'retrieval-r001.json').write_text(json.dumps(ledger, indent=2, allow_nan=False))
