import datetime,hashlib,json,os,time,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_90f4fed27b7e4793';out=q/'inputs/public'
jobs={
 'geo-candidate-summaries':('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gds&id=100000081,200326641&retmode=json','.json'),
 'geo-direct-pmp22-retry':('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urllib.parse.urlencode({'db':'gds','term':'(Nrf2 OR NFE2L2 OR Keap1) AND PMP22','retmode':'json','retmax':100}),'.json'),
 'PMC3863807':('https://www.ebi.ac.uk/europepmc/webservices/rest/PMC3863807/fullTextXML','.xml'),
 'PMC3628945-bioc':('https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/PMC3628945/unicode','.json'),
 'GSE326641':('https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE326641&targ=self&form=text&view=full','.soft')
}
for key,(url,suffix) in jobs.items():
 rec={'url':url,'requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=90) as r:data=r.read();rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
  path=out/(key+suffix);assert not path.exists();path.write_bytes(data)
  rec.update(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),path=str(path.relative_to(q)))
  if suffix=='.xml':
   root=ET.fromstring(data);(out/(key+'.txt')).write_text('\n'.join(' '.join(e.itertext()) for e in root.iter() if e.tag in {'article-title','title','p','caption'}))
  elif key.endswith('-bioc'):
   d=json.loads(data);texts=[]
   for coll in d:
    for doc in coll.get('documents',[]):
     for p in doc.get('passages',[]):texts.append(json.dumps(p.get('infons',{}))+ '\n'+p.get('text',''))
   (out/(key+'.txt')).write_text('\n'.join(texts))
 except Exception as e:rec['error']=str(e)
 (out/(key+'-receipt.json')).write_text(json.dumps(rec,indent=2,allow_nan=False));print(key,rec)
 time.sleep(0.5)
