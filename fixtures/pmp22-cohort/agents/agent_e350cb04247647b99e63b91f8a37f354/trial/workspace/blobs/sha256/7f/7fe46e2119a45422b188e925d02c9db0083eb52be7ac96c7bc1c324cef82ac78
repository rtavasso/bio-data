import concurrent.futures, datetime, hashlib, json, urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'sources/primary'
items=[]
for pmc in ['PMC3298281','PMC7322568','PMC6077802','PMC5181599']:
 items += [(pmc+'-bioc-ascii.json',f'https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{pmc}/ascii'),(pmc+'.pdf',f'https://europepmc.org/articles/{pmc}?pdf=render')]
items += [('PMC7430845-supplements.zip','https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7430845/supplementaryFiles')]
def get(item):
 name,url=item; rec={'url':url,'requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=90) as r:
   b=r.read();rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
  p=OUT/name;p.write_bytes(b);rec.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
  if name.endswith('.pdf'):rec['payload_valid']=b.startswith(b'%PDF')
  elif name.endswith('.zip'):
   rec['payload_valid']=zipfile.is_zipfile(p)
   if rec['payload_valid']:
    with zipfile.ZipFile(p) as z: print('MEMBERS',z.namelist())
  else:
   d=json.loads(b);rec['payload_valid']=isinstance(d,list) and bool(d)
   if rec['payload_valid']:
    (OUT/name.replace('.json','.txt')).write_text('\n\n'.join('[passage '+str(i)+'] '+v.get('text','') for item in d for doc in item.get('documents',[]) for i,v in enumerate(doc.get('passages',[]),1)))
 except Exception as e:rec.update(error=str(e),payload_valid=False)
 (OUT/(name+'.receipt.json')).write_text(json.dumps(rec,indent=2)+'\n');print(name,rec)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:list(ex.map(get,items))
