"""Extract readable primary HTML without executing its content."""
from html.parser import HTMLParser
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
class Reader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip=0
        self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):
            self.skip+=1
        if tag in ('p','h1','h2','h3','h4','section','tr','li') and not self.skip:
            self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip:
            self.skip-=1
        if tag in ('p','h1','h2','h3','h4','tr','li') and not self.skip:
            self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:
            self.parts.append(data)
p=Q/'inputs/primary/PMC5181599.html'
r=Reader()
r.feed(p.read_text())
lines=[' '.join(x.split()) for x in ''.join(r.parts).splitlines() if x.strip()]
p.with_suffix('.txt').write_text('\n'.join(lines)+'\n')
print('Extracted',len(lines),'lines')
