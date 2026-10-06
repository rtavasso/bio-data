"""Primary XML transport with exact per-attempt receipts; do not execute source content."""
import datetime,hashlib,json,os,shutil
from pathlib import Path
import httpx
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
dest=q/'inputs/primary';dest.mkdir(exist_ok=True,parents=True)
ids=['PMC5960709','PMC9405209','PMC9469140','PMC7067678','PMC11409949']
with httpx.Client(timeout=90,follow_redirects=True) as client:
    for pmc in ids:
        p=dest/f'{pmc}.xml'; rpath=dest/f'{pmc}.receipt.json'
        if rpath.exists(): print(pmc,'already recorded');continue
        free=shutil.disk_usage(q).free
        record={'requested_url':f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML','started_utc':datetime.datetime.now(datetime.UTC).isoformat(),'free_bytes_before':free}
        try:
            r=client.get(record['requested_url']); data=r.content;p.write_bytes(data)
            record.update(status=r.status_code,final_url=str(r.url),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),content_type=r.headers.get('content-type'),path=str(p.relative_to(q)))
        except Exception as exc: record['error']=repr(exc)
        record['ended_utc']=datetime.datetime.now(datetime.UTC).isoformat();rpath.write_text(json.dumps(record,indent=2))
        print(pmc,record.get('status'),record.get('bytes'),record.get('error'))
