"""Retrieve linked supplementary measurements without executing them."""
import hashlib
import json
import os
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
import httpx
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
d=q/'inputs/public'
class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            href=dict(attrs).get('href','')
            if '12974_2022_2462_MOESM4_ESM.xlsx' in href:
                self.links.append(href)
def get(client,url,name):
    p=d/name
    assert not p.exists()
    r=client.get(url)
    p.write_bytes(r.content)
    rec={'requested_url':url,'final_url':str(r.url),'status':r.status_code,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'success':r.is_success,'content_type':r.headers.get('content-type')}
    p.with_name(name+'.receipt.json').write_text(json.dumps(rec,indent=2))
    print(name,r.status_code,len(r.content),str(r.url))
    r.raise_for_status()
    return r
with httpx.Client(timeout=120,follow_redirects=True) as c:
    r=get(c,'https://link.springer.com/article/10.1186/s12974-022-02462-6','repair-publisher.html')
    parser=Links()
    parser.feed(r.text)
    urls=sorted({urljoin(str(r.url),s) for s in parser.links})
    assert len(urls)==1,urls
    r=get(c,urls[0],'repair-supp4.xlsx')
    assert r.content[:2]==b'PK', 'Not an XLSX ZIP container'
