"""Inspect saved metadata and native archives without running contained material."""
import json
import zipfile
from pathlib import Path
from html.parser import HTMLParser

Q=Path(__file__).resolve().parents[1]
p=Q/'inputs/public/PMP22-discovery.json'
d=json.loads(p.read_text())
print('DISCOVERY hitCount', d['hitCount'], 'returned',len(d['resultList']['result']))
for r in d['resultList']['result']:
    title=r.get('title','')
    if any(t in title.lower() for t in ('stem','schwann','dosage','pmp22','organoid','isogenic')):
        print(r.get('id'),r.get('pmcid'),r.get('firstPublicationDate'), title)
for p in (Q/'inputs/public').glob('*supp.zip'):
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:
            print('ARCHIVE',p.name,[(i.filename,i.file_size) for i in z.infolist()])
    else:
        print('NOT_ZIP',p.name,p.stat().st_size)
class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.out=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.skip+=1
        if tag in ('p','div','h1','h2','h3','table','tr'):self.out.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:self.out.append(data)
p=Q/'inputs/public/PMC2724915.html'
h=Text(); h.feed(p.read_text())
(Q/'inputs/text/PMC2724915.html.txt').write_text('\n'.join(s.strip() for s in ''.join(h.out).splitlines() if s.strip()))
