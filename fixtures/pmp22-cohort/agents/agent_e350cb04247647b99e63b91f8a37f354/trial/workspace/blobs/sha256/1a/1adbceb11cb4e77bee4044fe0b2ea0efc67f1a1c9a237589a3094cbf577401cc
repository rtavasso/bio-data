import concurrent.futures, datetime, hashlib, json, urllib.request
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'sources/primary'
items=[('rn5-refGene-Pmp22.json','https://api.genome.ucsc.edu/getData/track?genome=rn5;track=refGene;chrom=chr10;start=49315000;end=49350000')]
for pmc in ['PMC3298281','PMC7322568','PMC6077802','PMC5181599']:
 items += [(pmc+'-legacy.html',f'https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc}/'),(pmc+'-europe.html',f'https://europepmc.org/articles/{pmc}')]
def get(item):
 name,url=item;rec={'url':url,'requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=60) as r:
   b=r.read();rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
  (OUT/name).write_bytes(b);rec.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
  if name.endswith('.json'):
   d=json.loads(b);rec['payload_valid']='refGene' in d; print('UCSC',d)
  else:rec['payload_valid']=len(b)>50000 and b'Checking your browser' not in b[:10000]
 except Exception as e:rec.update(error=str(e),payload_valid=False)
 (OUT/(name+'.receipt.json')).write_text(json.dumps(rec,indent=2)+'\n');print(name,rec)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:list(ex.map(get,items))
