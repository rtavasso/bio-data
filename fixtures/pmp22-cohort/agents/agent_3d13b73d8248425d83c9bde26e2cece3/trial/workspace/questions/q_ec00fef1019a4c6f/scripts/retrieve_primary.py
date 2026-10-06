"""Preserve exact primary-source HTTP responses and real retrieval receipts."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import httpx

q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_ec00fef1019a4c6f'
d = q / 'inputs/public'
d.mkdir(parents=True, exist_ok=True)
urls = {
    'nae1-paper.json': 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:38608019%20AND%20SRC:MED&format=json&resultType=core',
    'snat.xml': 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC8064760/fullTextXML',
    'repair-paper.json': 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:35501870%20AND%20SRC:MED&format=json&resultType=core',
    'nae1-discovery.json': 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=Nae1%20AND%20Schwann&format=json&pageSize=30&resultType=core',
    'matched-discovery.json': 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=Schwann%20AND%20%22single%20cell%22%20AND%20knockout&format=json&pageSize=50&resultType=core',
}
with httpx.Client(timeout=90, follow_redirects=True) as client:
    for name, url in urls.items():
        dest = d / name
        receipt_path = d / (name + '.receipt.json')
        if dest.exists() or receipt_path.exists():
            raise RuntimeError(f'Refusing to overwrite request: {name}')
        rec = {'requested_url': url, 'retrieved_utc': datetime.now(timezone.utc).isoformat()}
        try:
            r = client.get(url)
            dest.write_bytes(r.content)
            rec.update(status=r.status_code, final_url=str(r.url), bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest(), content_type=r.headers.get('content-type'), path=str(dest), success=r.is_success)
        except Exception as exc:
            rec.update(success=False, error=repr(exc))
        receipt_path.write_text(json.dumps(rec, indent=2, allow_nan=False))
        print(name, rec.get('status'), rec.get('bytes'), rec.get('error'))
