import concurrent.futures
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

out = Path(__file__).resolve().parents[1] / 'inputs/public'
urls = {
    'PMC5800313.html': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5800313/',
    'nae1-supplement-epmc.pdf': 'https://europepmc.org/articles/PMC11014456/bin/sciadv.adm7600_sm.pdf',
}
def fetch(item):
    name, url = item
    path = out / name
    assert not path.exists()
    receipt = {'requested_url': url, 'started_utc': datetime.now(timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'bio-research-source-audit/1.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read(15_000_001)
            receipt.update(status=r.status, final_url=r.url, headers=dict(r.headers))
        path.write_bytes(body)
        receipt.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), first_bytes=repr(body[:30]), truncated=len(body)>15_000_000)
    except Exception as exc:
        receipt['error'] = repr(exc)
    receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (out / (name + '.receipt.json')).write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    return {k: v for k, v in receipt.items() if k != 'headers'}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for rec in pool.map(fetch, urls.items()):
        print(json.dumps(rec))
