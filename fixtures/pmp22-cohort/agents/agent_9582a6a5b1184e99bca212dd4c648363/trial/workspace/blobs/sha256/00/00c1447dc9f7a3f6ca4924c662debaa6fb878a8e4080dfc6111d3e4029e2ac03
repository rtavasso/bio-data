from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

OUT=Path(__file__).resolve().parents[1]/'sources/primary'
class Text(HTMLParser):
 def __init__(self): super().__init__(); self.parts=[]; self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ['script','style']: self.skip+=1
  if tag in ['p','h1','h2','h3','h4','tr','li']: self.parts.append('\n\n')
 def handle_endtag(self,tag):
  if tag in ['script','style']: self.skip=max(0,self.skip-1)
 def handle_data(self,text):
  if not self.skip:self.parts.append(text)

def get(item):
 name,url=item
 rec={'url':url,'requested_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=90) as r:
   b=r.read();rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
  dest=OUT/name;dest.write_bytes(b)
  rec.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
  if name.endswith('.html'):
   parser=Text();parser.feed(b.decode()); text=''.join(parser.parts)
   rec['payload_valid']=len(text)>10000 and 'Checking your browser' not in text[:3000]
  elif name.endswith('.xml'):
   tree=ET.fromstring(b);assert tree.tag=='article'
   text='\n\n'.join(f"[{e.tag} id={e.attrib.get('id','')}] "+''.join(e.itertext()) for e in tree.iter() if e.tag in ['article-title','title','p','table','caption'])
   rec['payload_valid']=True
  else: text='';rec['payload_valid']= b[:2]==b'\x1f\x8b'
  if text:dest.with_suffix('.txt').write_text(text)
 except Exception as e:rec.update(error=str(e),payload_valid=False)
 (OUT/(name+'.receipt.json')).write_text(json.dumps(rec,indent=2)+'\n')
 print(name,rec)
items=[(p+'.html',f'https://pmc.ncbi.nlm.nih.gov/articles/{p}/') for p in ['PMC3100536','PMC3298281','PMC7322568','PMC6077802','PMC5181599']]
items += [('PMC7145652.xml','https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7145652/fullTextXML'),('GSE139321.txt.gz','https://www.ncbi.nlm.nih.gov/geo/download/?acc=GSE139321&format=file&file=GSE139321%5FSchwann%5FCell%5FTn5Prime%5FGEO%5FProcessed%2Etxt%2Egz')]
with ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(get,items))
