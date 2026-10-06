"""Retrieve primary XML/metadata only; no code is downloaded or executed."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'sources/primary'
OUT.mkdir(parents=True,exist_ok=True)
ids=['PMC3100536','PMC3298281','PMC7322568','PMC6077802','PMC7430845','PMC6482019']

def get(pmc):
 url=f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML'
 dest=OUT/(pmc+'.xml')
 receipt={'url':url,'requested_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=90) as r:
   b=r.read(); receipt.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
  dest.write_bytes(b)
  receipt.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
  tree=ET.fromstring(b)
  assert tree.tag=='article'
  receipt['payload_valid']=True
  blocks=[]
  for e in tree.iter():
   if e.tag in ['article-title','title','p','table','caption']:
    blocks.append(f"[{e.tag} id={e.attrib.get('id','')}] "+''.join(e.itertext()))
  (OUT/(pmc+'.txt')).write_text('\n\n'.join(blocks)+'\n')
 except Exception as e:
  receipt['error']=str(e); receipt['payload_valid']=False
 (OUT/(pmc+'.receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n')
 print(pmc,receipt)
with ThreadPoolExecutor(max_workers=4) as ex: list(ex.map(get,ids))
