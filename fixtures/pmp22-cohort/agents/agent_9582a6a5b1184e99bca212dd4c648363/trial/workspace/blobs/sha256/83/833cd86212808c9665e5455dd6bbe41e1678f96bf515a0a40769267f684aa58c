"""Bounded alternative source retrieval with explicit payload checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
OUT=Path(__file__).resolve().parents[1]/'sources/primary'
ids=['PMC3100536','PMC3298281','PMC7322568','PMC6077802','PMC5181599']
items=[]
for pmc in ids:
 items.extend([(pmc+'-bioc.xml',f'https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/{pmc}/unicode'),(pmc+'-meta.json','https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':pmc,'format':'json','resultType':'core'}))])

def get(item):
 name,url=item;rec={'url':url,'requested_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=90) as r:
   b=r.read();rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
  (OUT/name).write_bytes(b);rec.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
  if name.endswith('.json'):
   data=json.loads(b);rec['payload_valid']=True
   for x in data.get('resultList',{}).get('result',[]):print('META',x.get('pmcid'),x.get('title'),x.get('doi'),x.get('fullTextUrlList'))
  else:
   tree=ET.fromstring(b);rec['root']=tree.tag;rec['payload_valid']=tree.tag=='collection'
   if rec['payload_valid']:
    passages=['[passage '+str(i)+'] '+''.join(e.findtext('text','')) for i,e in enumerate(tree.iter('passage'),1)]
    (OUT/name.replace('.xml','.txt')).write_text('\n\n'.join(passages)+'\n')
 except Exception as e:rec.update(error=str(e),payload_valid=False)
 (OUT/(name+'.receipt.json')).write_text(json.dumps(rec,indent=2)+'\n');print(name,rec)
with ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(get,items))
tree=ET.parse(OUT/'PMC7430845.xml')
for e in tree.iter():
 if e.tag in ['supplementary-material','ext-link','media']:
  if e.tag!='ext-link' or any(t in ''.join(e.itertext()) for t in ['http','GSE']): print('TSS LINK',e.tag,e.attrib,''.join(e.itertext())[:300])
