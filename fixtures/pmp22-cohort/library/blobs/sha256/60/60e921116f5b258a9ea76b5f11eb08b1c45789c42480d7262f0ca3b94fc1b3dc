import datetime,hashlib,json,os,urllib.parse,urllib.request
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_90f4fed27b7e4793'
out=q/'inputs/public'
queries={
'geo-direct-matched':'(Nae1 OR neddylation OR MLN4924) AND (Nrf2 OR NFE2L2) AND (Schwann OR nerve OR PMP22)',
'geo-direct-schwann':'(Nrf2 OR NFE2L2) AND Schwann',
'geo-direct-neddylation':'(Nrf2 OR NFE2L2) AND (MLN4924 OR neddylation OR Nae1)',
'geo-direct-pmp22':'(Nrf2 OR NFE2L2 OR Keap1) AND PMP22'
}
for key,term in queries.items():
 url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urllib.parse.urlencode({'db':'gds','term':term,'retmode':'json','retmax':100})
 rec={'query':term,'url':url,'requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=60) as r:data=r.read();rec.update(status=r.status)
  (out/(key+'.json')).write_bytes(data)
  rec.update(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),result=json.loads(data))
 except Exception as e:rec['error']=str(e)
 (out/(key+'-receipt.json')).write_text(json.dumps(rec,indent=2,allow_nan=False));print(json.dumps(rec))
url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':'DOI:10.1016/j.nbd.2013.01.003','format':'json','resultType':'core'})
with urllib.request.urlopen(url,timeout=60) as r:data=r.read()
(out/'search-nrf2-injury-exact.json').write_bytes(data)
print('injury',json.loads(data))
