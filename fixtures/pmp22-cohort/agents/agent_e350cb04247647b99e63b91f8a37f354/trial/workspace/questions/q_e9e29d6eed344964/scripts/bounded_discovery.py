import concurrent.futures, datetime, hashlib, json, urllib.parse, urllib.request
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'sources/primary'
queries={'pmp22-cis-nascent':'PMP22 AND (nascent OR CRISPR OR promoter OR enhancer)','schwann-tss-assays':'Schwann AND (RAMPAGE OR CAGE OR Tn5Prime)','schwann-cis-perturbation':'Schwann AND (CRISPRi OR "enhancer deletion")'}
items=[(name+'-search.json','https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':q,'format':'json','resultType':'core','pageSize':50})) for name,q in queries.items()]
items += [('NM_017037.gb','https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=NM_017037&rettype=gb&retmode=text')]
for doi,name in [('ddaa082','PMC7322568'),('ddy191','PMC6077802'),('ddr595','PMC3298281'),('ddw158','PMC5181599')]:items.append((name+'-publisher.html',f'https://academic.oup.com/hmg/article-lookup/doi/10.1093/hmg/{doi}'))
def get(item):
 name,url=item;rec={'url':url,'requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=60) as r:
   b=r.read();rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
  (OUT/name).write_bytes(b);rec.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
  if name.endswith('.json'):
   d=json.loads(b);rec['payload_valid']=True;print('SEARCH',name,'hits',d.get('hitCount'))
   for x in d.get('resultList',{}).get('result',[]):print(x.get('id'),x.get('pmcid'),x.get('title'))
  elif name.endswith('.gb'):rec['payload_valid']=b.startswith(b'LOCUS')
  else:rec['payload_valid']=len(b)>50000 and b'<title>Just a moment' not in b[:10000]
 except Exception as e:rec.update(error=str(e),payload_valid=False)
 (OUT/(name+'.receipt.json')).write_text(json.dumps(rec,indent=2)+'\n');print('RECEIPT',name,rec)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:list(ex.map(get,items))
