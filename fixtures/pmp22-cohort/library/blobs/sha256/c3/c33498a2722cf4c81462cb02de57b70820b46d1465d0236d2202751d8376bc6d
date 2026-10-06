"""Resolve candidate sibling metadata; preserve errors and bytes, never execute data."""
import datetime
import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_90f4fed27b7e4793'
for acc in ['GSE326639', 'GSE326642']:
    url = 'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?' + urllib.parse.urlencode(
        {'acc': acc, 'targ': 'self', 'form': 'text', 'view': 'full'})
    path = q / 'inputs/public' / (acc + '.soft')
    receipt = {'url': url, 'requested_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'purpose': 'candidate sibling metadata discovery; accession is not presupposed applicable'}
    try:
        with urllib.request.urlopen(url, timeout=45) as response:
            raw = response.read()
            receipt.update(status=response.status, final_url=response.url)
        assert not path.exists()
        path.write_bytes(raw)
        receipt.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), path=str(path.relative_to(q)))
    except Exception as exc:
        receipt['error'] = str(exc)
    (q / 'inputs/public' / (acc + '-receipt.json')).write_text(json.dumps(receipt, indent=2, allow_nan=False))
    print(json.dumps(receipt, allow_nan=False))
