import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
urls=json.loads((Path(sys.argv[1]) if len(sys.argv)>1 else q/'inputs/followup-urls.json').read_text())
with httpx.Client(timeout=90,follow_redirects=True) as client:
    for name,url in urls.items():
        p=q/'inputs/public'/name
        rec_path=p.with_name(p.name+'.receipt.json')
        assert not p.exists() and not rec_path.exists()
        rec={'requested_url':url,'retrieved_utc':datetime.now(timezone.utc).isoformat()}
        try:
            r=client.get(url)
            p.write_bytes(r.content)
            rec.update(status=r.status_code,final_url=str(r.url),bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest(),content_type=r.headers.get('content-type'),success=r.is_success,path=str(p))
        except Exception as exc:
            rec.update(success=False,error=repr(exc))
        rec_path.write_text(json.dumps(rec,indent=2,allow_nan=False))
        print(name,rec.get('status'),rec.get('bytes'),rec.get('error'))
