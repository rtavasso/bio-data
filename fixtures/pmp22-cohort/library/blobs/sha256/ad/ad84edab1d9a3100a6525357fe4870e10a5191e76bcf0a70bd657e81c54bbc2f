"""Retrieve explicitly selected primary sources with per-attempt receipts and disk reserve."""
import datetime,hashlib,json,os,shutil,sys
from pathlib import Path
import httpx
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
config=json.loads((q/'outputs/doctor.json').read_text())['budgets']
urls=json.loads(Path(sys.argv[1]).read_text())
with httpx.Client(timeout=90,follow_redirects=True) as client:
    for name,url in urls.items():
        p=q/'inputs/public'/name;p.parent.mkdir(parents=True,exist_ok=True)
        rp=p.with_name(p.name+'.receipt.json')
        if rp.exists(): print(name,'existing receipt');continue
        receipt={'requested_url':url,'started_utc':datetime.datetime.now(datetime.UTC).isoformat(),'reserve_bytes':config['reserve_bytes']}
        try:
            assert shutil.disk_usage(q).free>config['reserve_bytes'], 'disk reserve'
            with client.stream('GET',url) as r:
                receipt.update(status=r.status_code,final_url=str(r.url),headers=dict(r.headers))
                h=hashlib.sha256();n=0
                with p.open('xb') as out:
                    for chunk in r.iter_bytes():
                        assert shutil.disk_usage(q).free-len(chunk)>config['reserve_bytes'], 'disk reserve'
                        out.write(chunk);h.update(chunk);n+=len(chunk)
                receipt.update(bytes=n,sha256=h.hexdigest(),path=str(p.relative_to(q)))
        except Exception as e: receipt['error']=repr(e)
        receipt['ended_utc']=datetime.datetime.now(datetime.UTC).isoformat();rp.write_text(json.dumps(receipt,indent=2))
        print(name,receipt.get('status'),receipt.get('bytes'),receipt.get('error'))
