"""Recover failed full text via PMC HTML; no source code is executed."""
import json,hashlib,textwrap
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from html.parser import HTMLParser
class Text(HTMLParser):
    def __init__(self): super().__init__();self.skip=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if not self.skip and tag in ('p','div','section','h1','h2','h3','li','tr'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip:self.skip-=1
        if not self.skip and tag in ('p','div','section','h1','h2','h3','li','tr'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/primary';R=[]
for p in ['PMC6128698','PMC13520134','PMC11563883']:
    url=f'https://pmc.ncbi.nlm.nih.gov/articles/{p}/';r={'url':url,'started':datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url,headers={'User-Agent':'bio-data-research/1.0'}),timeout=100) as f:
            data=f.read();r.update(status=f.status,headers=dict(f.headers),final_url=f.url)
    except HTTPError as e:data=e.read();r.update(status=e.code,error=str(e))
    except Exception as e:data=b'';r['error']=repr(e)
    name=p+'-retry.html';assert not(D/name).exists();(D/name).write_bytes(data)
    r.update(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    parser=Text();parser.feed(data.decode(errors='replace'))
    text='\n\n'.join(textwrap.fill(' '.join(x.split()),width=150) for x in ''.join(parser.parts).splitlines() if x.strip())
    (D/(p+'-retry.txt')).write_text(text+'\n');r['parsed_text_chars']=len(text)
    R.append(r);(D/'transport-paper-r002.json').write_text(json.dumps(R,indent=2)+'\n');print(p,r.get('status'),r['bytes'],r['parsed_text_chars'],text[:80])
