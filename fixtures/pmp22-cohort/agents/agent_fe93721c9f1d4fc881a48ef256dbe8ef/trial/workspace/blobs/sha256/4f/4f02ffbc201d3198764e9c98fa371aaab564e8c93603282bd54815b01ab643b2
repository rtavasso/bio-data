"""Explicit bounded retrieval of primary publications; save exact bytes and receipts."""
import concurrent.futures
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

q = Path(__file__).resolve().parents[1]
out = q / 'inputs' / 'public'
out.mkdir(parents=True, exist_ok=True)
sources = {
    'PMC5800313.xml': 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC5800313/fullTextXML',
    'PMC11592338.xml': 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11592338/fullTextXML',
    'nae1-main.pdf': 'https://eprints.gla.ac.uk/324744/1/324744.pdf',
    'nae1-supplement.pdf': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC11014456/bin/sciadv.adm7600_sm.pdf',
}

def fetch(item):
    name, url = item
    path = out / name
    if path.exists():
        raise FileExistsError(path)
    record = {'name': name, 'requested_url': url, 'started_utc': datetime.now(timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'bio-research-source-audit/1.0'})
        with urllib.request.urlopen(req, timeout=90) as response:
            body = response.read(35_000_001)
            if len(body) > 35_000_000:
                raise ValueError('source exceeds explicit 35 MB per-file bound')
            record.update(status=response.status, final_url=response.url, headers=dict(response.headers))
        path.write_bytes(body)
        record.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        record['valid_expected_format'] = body.startswith(b'%PDF') if name.endswith('.pdf') else b'<article' in body
    except Exception as exc:
        record['error'] = repr(exc)
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (out / (name + '.receipt.json')).write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
    return record

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for receipt in pool.map(fetch, sources.items()):
        print(json.dumps({k: v for k, v in receipt.items() if k != 'headers'}, allow_nan=False))
