"""Snapshot structured provider metadata for existing quantitative exports only."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'inputs/public'
queries=[('PXD023091-project.json','https://www.ebi.ac.uk/pride/ws/archive/v2/projects/PXD023091'),('PXD023091-files.json','https://www.ebi.ac.uk/pride/ws/archive/v2/projects/PXD023091/files?pageSize=100&page=0'),('PXD043917-project-current.json','https://www.ebi.ac.uk/pride/ws/archive/v2/projects/PXD043917'),('PXD043917-files-current.json','https://www.ebi.ac.uk/pride/ws/archive/v2/projects/PXD043917/files?pageSize=100&page=0')]
for name,url in queries:
    p=OUT/name
    if p.exists():
        raise RuntimeError('no overwrite')
    r=httpx.get(url,timeout=90,follow_redirects=True)
    p.write_bytes(r.content)
    receipt={'url':url,'final_url':str(r.url),'status':r.status_code,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'headers':dict(r.headers),'body':str(p.relative_to(ROOT))}
    (OUT/(name+'.receipt.json')).write_text(json.dumps(receipt,indent=2))
    print(name,r.status_code,len(r.content))
    if r.status_code==200:
        doc=r.json()
        (OUT/(name+'.pretty.json')).write_text(json.dumps(doc,indent=2))
        print(json.dumps(doc)[:2400])
