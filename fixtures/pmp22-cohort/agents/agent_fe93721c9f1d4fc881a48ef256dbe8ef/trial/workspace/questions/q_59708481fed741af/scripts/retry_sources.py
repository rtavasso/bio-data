import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

out = Path(__file__).resolve().parents[1] / 'inputs/public'
urls = {
    'PMC5800313.retry.xml': 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC5800313/fullTextXML',
    'nae1-supplement-science.pdf': 'https://www.science.org/doi/suppl/10.1126/sciadv.adm7600/suppl_file/sciadv.adm7600_sm.pdf',
    'PMC11014456-suppfiles.zip': 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11014456/supplementaryFiles',
}
for name, url in urls.items():
    path = out / name
    assert not path.exists()
    receipt = {'requested_url': url, 'started_utc': datetime.now(timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'bio-research-source-audit/1.0'})
        with urllib.request.urlopen(req, timeout=75) as r:
            body = r.read(40_000_001)
            if len(body) > 40_000_000:
                raise ValueError('supplement exceeds 40 MB bounded request')
            receipt.update(status=r.status, final_url=r.url, headers=dict(r.headers))
        path.write_bytes(body)
        receipt.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), first_bytes=repr(body[:30]))
    except Exception as exc:
        receipt['error'] = repr(exc)
    receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (out / (name + '.receipt.json')).write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'headers'}))
