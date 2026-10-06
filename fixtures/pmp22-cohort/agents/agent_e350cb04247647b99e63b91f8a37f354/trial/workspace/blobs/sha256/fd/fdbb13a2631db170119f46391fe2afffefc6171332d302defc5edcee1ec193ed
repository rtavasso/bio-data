from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib, json, urllib.request
from pathlib import Path
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
OUT=Path(__file__).resolve().parents[1]/'sources/primary'
items=[('PMC10959528.xml','https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10959528/fullTextXML'),('PMID42801440-publisher.html','https://link.springer.com/article/10.1007/s13770-026-00837-x'),('PMC6077802-oup.pdf','https://academic.oup.com/hmg/article-pdf/27/16/2830/25428252/ddy191.pdf')]
def get(item):
 name,url=item;rec={'url':url,'requested_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=90) as r:
   b=r.read();rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
  (OUT/name).write_bytes(b);rec.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
  if name.endswith('.xml'):
   tree=ET.fromstring(b);rec['payload_valid']=tree.tag=='article'
   text='\n\n'.join(f"[{e.tag} id={e.attrib.get('id','')}] "+''.join(e.itertext()) for e in tree.iter() if e.tag in ['article-title','title','p','table','caption'])
   (OUT/name.replace('.xml','.txt')).write_text(text)
  elif name.endswith('.pdf'):rec['payload_valid']=b.startswith(b'%PDF')
  else:rec['payload_valid']=len(b)>50000 and b'Client Challenge' not in b[:20000]
 except Exception as e:rec.update(error=str(e),payload_valid=False)
 (OUT/(name+'.receipt.json')).write_text(json.dumps(rec,indent=2)+'\n');print(name,rec)
with ThreadPoolExecutor(max_workers=3) as ex:list(ex.map(get,items))
