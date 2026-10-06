import datetime,hashlib,json,os,time,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_90f4fed27b7e4793';out=q/'inputs/public'
jobs={'PMC13421985':('https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13421985/fullTextXML','.xml')}
for acc in ['GSM9636029','GSM9636030','GSM9636031','GSM9636032','GSM9636033','GSM9636034','GSM9636035','GSM9636036']:
 jobs[acc]=('https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?'+urllib.parse.urlencode({'acc':acc,'targ':'self','form':'text','view':'full'}),'.soft')
for key,(url,suffix) in jobs.items():
 rec={'key':key,'url':url,'requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(url,timeout=90) as r:data=r.read();rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
  path=out/(key+suffix);assert not path.exists();path.write_bytes(data)
  rec.update(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),path=str(path.relative_to(q)))
  if suffix=='.xml':
   root=ET.fromstring(data);(out/(key+'.txt')).write_text('\n'.join(' '.join(e.itertext()) for e in root.iter() if e.tag in {'article-title','title','p','caption'}))
 except Exception as e:rec['error']=str(e)
 (out/(key+'-receipt.json')).write_text(json.dumps(rec,indent=2,allow_nan=False));print(key,rec.get('status'),rec.get('bytes'),rec.get('error'))
 time.sleep(0.6)
