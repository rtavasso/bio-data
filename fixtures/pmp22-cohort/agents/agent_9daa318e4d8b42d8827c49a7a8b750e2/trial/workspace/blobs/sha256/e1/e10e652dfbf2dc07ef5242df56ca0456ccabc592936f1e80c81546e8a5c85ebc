"""Bounded HTTPS acquisition; exact bytes, verified TLS, receipts; no downloaded code execution."""
import pathlib,json,urllib.request,urllib.error,hashlib,datetime,sys
Q=pathlib.Path(__file__).resolve().parents[1]; D=Q/'inputs/iteration';D.mkdir(exist_ok=True)
LEDGER=D/'transport.json'
def read():return json.loads(LEDGER.read_text()) if LEDGER.exists() else {'request_limit':150,'byte_limit':1073741824,'file_limit':536870912,'entries':[],'external_tool_requests':0,'external_tool_bytes':0}
def save(d):LEDGER.write_text(json.dumps(d,indent=2,allow_nan=False))
def fetch(url,name,cap=536870912):
 p=D/name
 if p.exists():print('EXISTS',name,p.stat().st_size);return p
 d=read();used=sum(e.get('bytes',0) for e in d['entries'])+d['external_tool_bytes'];n=len(d['entries'])+d['external_tool_requests']
 if n>=150:raise RuntimeError('request budget exhausted')
 cap=min(cap,536870912,1073741824-used)
 if cap<=0:raise RuntimeError('byte budget exhausted')
 e={'url':url,'path':str(p.relative_to(Q)),'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bytes':0};d['entries'].append(e);save(d)
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,req,fp,code,msg,headers,newurl):return None
 try:
  op=urllib.request.build_opener(NoRedirect)
  with op.open(urllib.request.Request(url,headers={'User-Agent':'PMP22-research/1.0'}),timeout=50) as r:
   e.update(status=r.status,headers=dict(r.headers));h=hashlib.sha256()
   if int(r.headers.get('Content-Length','0'))>cap:raise RuntimeError('content-length exceeds remaining cap')
   with p.open('wb') as f:
    while True:
     b=r.read(min(1024*1024,cap-e['bytes']+1))
     if not b:break
     e['bytes']+=len(b);h.update(b);f.write(b)
     if e['bytes']>cap:raise RuntimeError('byte cap exceeded')
   e['sha256']=h.hexdigest();e['completed']=True
 except urllib.error.HTTPError as err:
  e.update(status=err.code,error=str(err),headers=dict(err.headers))
  save(d)
  if err.code in (301,302,303,307,308):
   return fetch(urllib.parse.urljoin(url,err.headers['Location']),name,cap)
 except Exception as err:e['error']=repr(err)
 save(d);print(name,e.get('status'),e.get('bytes'),e.get('error',''))
 return p if e.get('completed') else None
if __name__=='__main__':
 import fcntl
 with (D/'transport.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  fetch(sys.argv[1],sys.argv[2])
