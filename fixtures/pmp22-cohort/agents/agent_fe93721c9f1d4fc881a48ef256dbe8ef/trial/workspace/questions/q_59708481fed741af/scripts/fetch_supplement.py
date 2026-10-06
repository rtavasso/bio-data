import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

q = Path(__file__).resolve().parents[1]
url = 'https://pmc.ncbi.nlm.nih.gov/articles/instance/11014456/bin/sciadv.adm7600_sm.pdf'
p = q / 'inputs/public/nae1-supplement-instance.pdf'
assert not p.exists()
r = {'requested_url': url, 'started_utc': datetime.now(timezone.utc).isoformat()}
try:
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'bio-research-source-audit/1.0'}), timeout=90) as f:
        b = f.read(30_000_001)
        r.update(status=f.status, final_url=f.url, headers=dict(f.headers))
    p.write_bytes(b)
    r.update(bytes=len(b), sha256=hashlib.sha256(b).hexdigest(), valid_pdf=b.startswith(b'%PDF'), truncated=len(b)>30_000_000)
except Exception as exc:
    r['error'] = repr(exc)
r['finished_utc'] = datetime.now(timezone.utc).isoformat()
p.with_suffix('.receipt.json').write_text(json.dumps(r, indent=2, allow_nan=False)+'\n')
print(json.dumps({k: v for k, v in r.items() if k != 'headers'}))
