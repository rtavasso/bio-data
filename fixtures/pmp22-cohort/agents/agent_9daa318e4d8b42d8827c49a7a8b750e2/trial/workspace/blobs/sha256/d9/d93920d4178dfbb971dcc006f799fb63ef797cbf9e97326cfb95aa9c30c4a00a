import urllib.request,json,pathlib,hashlib,time
q=pathlib.Path(__file__).resolve().parents[1]
ids=['PMC5181599','PMC7322568','PMC2713384','PMC6920087','PMC11592338','PMC4227013','PMC6607759']
receipts=[]
for ident in ids:
 url=f'https://www.ebi.ac.uk/europepmc/webservices/rest/{ident}/fullTextXML'
 try:
  with urllib.request.urlopen(url,timeout=25) as r:
   b=r.read(64*1024*1024+1)
   if len(b)>64*1024*1024: raise ValueError('size cap')
   (q/'inputs'/f'{ident}.xml').write_bytes(b)
   receipts.append({'url':url,'status':r.status,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'headers':dict(r.headers),'time':time.time()})
 except Exception as e: receipts.append({'url':url,'error':str(e),'time':time.time()})
 (q/'inputs/public-receipts.json').write_text(json.dumps(receipts,indent=2))
 print(ident,receipts[-1].get('bytes',receipts[-1].get('error')))
