"""Retrieve reference DNA for a bounded, exact source-primer mapping check."""
from datetime import datetime, timezone
import hashlib, json, urllib.request
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'sources/primary'
u='https://api.genome.ucsc.edu/getData/sequence?genome=rn5;chrom=chr10;start=49315000;end=49321500'
r={'url':u,'requested_utc':datetime.now(timezone.utc).isoformat()}
try:
 with urllib.request.urlopen(u,timeout=60) as x:
  b=x.read();r.update(status=x.status,final_url=x.url,content_type=x.headers.get('Content-Type'))
 d=json.loads(b);r.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),payload_valid=len(d.get('dna',''))==6500)
 (P/'rn5-Pmp22-promoter-sequence.json').write_bytes(b)
except Exception as e:r.update(payload_valid=False,error=str(e))
(P/'rn5-Pmp22-promoter-sequence.json.receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
