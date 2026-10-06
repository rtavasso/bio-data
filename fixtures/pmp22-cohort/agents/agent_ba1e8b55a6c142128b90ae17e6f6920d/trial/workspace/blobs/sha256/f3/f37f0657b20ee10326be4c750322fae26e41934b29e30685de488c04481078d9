"""TLS-verified source acquisition; receipts written per attempt, never execute bytes."""
from pathlib import Path
import requests, json, hashlib, datetime, sys, concurrent.futures
Q=Path(__file__).resolve().parents[1]; I=Q/'inputs/upstream'; R=I/'receipts'; R.mkdir(exist_ok=True)
def acquire(task):
    name,url=task['name'],task['url']; dest=I/name
    if dest.exists(): return {'name':name,'status':'already_exists_not_fetched'}
    rec=dict(name=name,url=url,started=datetime.datetime.now(datetime.timezone.utc).isoformat(),bytes=0,status='attempt')
    rp=R/(name.replace('/','_')+'.json');rp.write_text(json.dumps(rec,indent=2))
    try:
        with requests.get(url,stream=True,timeout=(20,120)) as r:
            rec.update(http_status=r.status_code,final_url=r.url,content_type=r.headers.get('Content-Type'),content_length=r.headers.get('Content-Length'),redirects=[{'url':x.url,'status':x.status_code} for x in r.history])
            h=hashlib.sha256();dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as f:
                for c in r.iter_content(262144):
                    if c:f.write(c);h.update(c);rec['bytes']+=len(c)
            rec['sha256']=h.hexdigest();rec['status']='downloaded_unvalidated';r.raise_for_status()
    except Exception as e:rec['status']='failed';rec['error']=str(e)
    rec['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat();rp.write_text(json.dumps(rec,indent=2));return rec
if __name__=='__main__':
    tasks=json.loads(Path(sys.argv[1]).read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(acquire,tasks):print(json.dumps(r))
    events=[json.loads(p.read_text()) for p in sorted(R.glob('*.json'))]
    browser=I/'web-searches.json'; b=json.loads(browser.read_text()) if browser.exists() else []
    d=dict(allowance='unlimited current-continuation requests/size/bytes/time',direct_requests=sum(1+len(e.get('redirects',[])) for e in events),downloaded_bytes=sum(e['bytes'] for e in events),browser_requests=sum(e['requests'] for e in b),browser_bytes_estimated=sum(e['estimated_bytes'] for e in b),events=events,browser_ledger='inputs/upstream/web-searches.json')
    (I/'transport.json').write_text(json.dumps(d,indent=2,allow_nan=False))
