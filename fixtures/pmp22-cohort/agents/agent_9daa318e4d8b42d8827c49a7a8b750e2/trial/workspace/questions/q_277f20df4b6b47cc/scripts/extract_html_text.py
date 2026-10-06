from html.parser import HTMLParser
import pathlib
class Text(HTMLParser):
 def __init__(self):super().__init__();self.skip=0;self.parts=[]
 def handle_starttag(self,t,a):
  if t in ['script','style']:self.skip+=1
  if t in ['p','h1','h2','h3','h4','section','figcaption','tr']:self.parts.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style']:self.skip=max(0,self.skip-1)
 def handle_data(self,s):
  if not self.skip:self.parts.append(s)
q=pathlib.Path(__file__).resolve().parents[1]
for f in (q/'inputs/continuation').glob('PMC*.html'):
 p=Text();p.feed(f.read_text());out=q/'outputs/source-text'/(f.stem+'.txt');out.write_text(''.join(p.parts))
