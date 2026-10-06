"""Retrieve one author-deposited thesis, validating its native PDF payload."""
from datetime import datetime, timezone
import hashlib, json, urllib.request
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'sources/primary'
u='https://asset.library.wisc.edu/1711.dl/PNF6PVIDN6ZSA9B/R/file-a2dbf.pdf'
r={'url':u,'requested_utc':datetime.now(timezone.utc).isoformat()}
try:
 with urllib.request.urlopen(u,timeout=90) as x:
  b=x.read();r.update(status=x.status,final_url=x.url,content_type=x.headers.get('Content-Type'))
 (P/'Pantera-thesis.pdf').write_bytes(b);r.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),payload_valid=b.startswith(b'%PDF'))
except Exception as e:r.update(payload_valid=False,error=str(e))
(P/'Pantera-thesis.pdf.receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
