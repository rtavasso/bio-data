"""Bounded primary XML retrieval; preserve successes and failures exactly."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx
from defusedxml import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'inputs/public'
OUT.mkdir(parents=True,exist_ok=True)
for pmc in ['PMC8191293','PMC4227013']:
    url=f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML'
    r=httpx.get(url,timeout=90,follow_redirects=True)
    raw=r.content
    sha=hashlib.sha256(raw).hexdigest()
    file=OUT/f'{pmc}.xml'
    if file.exists():
        raise RuntimeError('refusing to overwrite source')
    file.write_bytes(raw)
    receipt={'url':url,'final_url':str(r.url),'status':r.status_code,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(raw),'sha256':sha,'headers':dict(r.headers),'body':str(file.relative_to(ROOT))}
    (OUT/f'{pmc}.receipt.json').write_text(json.dumps(receipt,indent=2))
    print(pmc,r.status_code,len(raw),sha)
    r.raise_for_status()
    root=ET.fromstring(raw)
    parts=[]
    for el in root.iter():
        if el.tag in ['article-title','title','p','caption','table-wrap','supplementary-material']:
            txt=''.join(el.itertext())
            parts.append(f'{el.tag} id={el.get("id","")} '+txt)
    (OUT/f'{pmc}.txt').write_text('\n\n'.join(parts))
    print('SUPPLEMENTS',[(e.tag,e.attrib) for e in root.iter() if e.tag in ['supplementary-material','media','ext-link']])
