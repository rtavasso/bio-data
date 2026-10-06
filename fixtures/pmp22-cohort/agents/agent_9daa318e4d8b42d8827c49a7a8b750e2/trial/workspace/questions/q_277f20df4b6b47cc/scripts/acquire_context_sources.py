"""Bounded TLS-verified acquisition with serialized receipts; never executes sources."""
from pathlib import Path
import requests,json,hashlib,datetime,sys
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/context-audit';L=I/'transport.json'
url,name=sys.argv[1:];d=json.loads(L.read_text());assert d['requests']<150
r=dict(url=url,name=name,started=datetime.datetime.now(datetime.timezone.utc).isoformat(),bytes=0,status='attempt');d['requests']+=1;d['events'].append(r);L.write_text(json.dumps(d,indent=2))
try:
 with requests.get(url,timeout=50,stream=True) as resp:
  r['http_status']=resp.status_code;r['final_url']=resp.url;r['content_type']=resp.headers.get('Content-Type');p=I/name
  with p.open('xb') as f:
   for chunk in resp.iter_content(65536):
    if not chunk:continue
    if r['bytes']+len(chunk)>536870912 or d['downloaded_bytes']+d['web_estimated_bytes']+len(chunk)>1073741824:raise RuntimeError('transport cap')
    f.write(chunk);r['bytes']+=len(chunk);d['downloaded_bytes']+=len(chunk)
  r['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();r['status']='downloaded_unvalidated';resp.raise_for_status()
except Exception as e:r['error']=str(e);r['status']='failed';raise
finally:
 r['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat();L.write_text(json.dumps(d,indent=2));print(json.dumps(r))
