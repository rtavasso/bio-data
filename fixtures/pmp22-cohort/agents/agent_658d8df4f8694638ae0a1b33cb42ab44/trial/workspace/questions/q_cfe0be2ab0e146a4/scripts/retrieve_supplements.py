"""Retrieve only declared paper supplements, preserving HTTP bodies and receipts."""
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import httpx
from defusedxml import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'inputs/public'

def get(url,name):
    p=OUT/name
    if p.exists():
        saved=json.loads((OUT/(name+'.receipt.json')).read_text())
        raw=p.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==saved['sha256']
        # Saved bodies are decoded by httpx, so do not decode Content-Encoding twice.
        return httpx.Response(saved['status'],content=raw)
    r=httpx.get(url,timeout=120,follow_redirects=True)
    p.write_bytes(r.content)
    receipt={'url':url,'final_url':str(r.url),'status':r.status_code,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'headers':dict(r.headers),'body':str(p.relative_to(ROOT))}
    (OUT/(name+'.receipt.json')).write_text(json.dumps(receipt,indent=2))
    print(name,r.status_code,len(r.content),r.headers.get('content-type'))
    return r

for pmc in ['PMC8191293','PMC4227013']:
    r=get(f'https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmc}',f'{pmc}-oa.xml')
    links=[]
    if r.status_code == 200:
        root=ET.fromstring(r.content)
        links=[e.get('href') for e in root.iter('link') if e.get('format')=='tgz']
    for link in links:
        print('OA package locator',link)
    # Europe PMC offers just supplements; no raw proteomics processing.
    r=get(f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/supplementaryFiles',f'{pmc}-supplements.bin')
    if r.status_code==200 and r.content[:2]==b'PK':
        import zipfile
        z=zipfile.ZipFile(BytesIO(r.content))
        print('ZIP MEMBERS',z.namelist())
        for item in z.infolist():
            if item.filename.endswith(('.xlsx','.pdf')) and item.file_size<20_000_000:
                dest=OUT/(pmc+'-'+Path(item.filename).name)
                raw=z.read(item)
                if dest.exists():
                    raise RuntimeError('already exists')
                dest.write_bytes(raw)
                print('PRESERVED',dest.name,len(raw),hashlib.sha256(raw).hexdigest())
    elif r.status_code==200:
        try:
            z=tarfile.open(fileobj=BytesIO(r.content))
            print('TAR MEMBERS',[m.name for m in z.getmembers()])
        except tarfile.ReadError:
            print('NOT A RECOGNIZED SUPPLEMENT ARCHIVE')
