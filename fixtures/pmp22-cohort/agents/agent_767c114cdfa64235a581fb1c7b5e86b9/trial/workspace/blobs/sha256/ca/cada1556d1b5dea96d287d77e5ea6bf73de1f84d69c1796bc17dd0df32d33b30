"""Extract primary JATS text/links, preserving locators; no source code execution."""
from pathlib import Path
import json,re,sys
from defusedxml import ElementTree as ET
Q=Path(__file__).resolve().parents[1]; O=Q/'outputs/upstream';I=Q/'inputs/upstream'
for name in sys.argv[1:]:
 p=I/name
 try:root=ET.parse(p).getroot()
 except Exception as e:print(name,repr(e));continue
 assert root.tag=='article',root.tag
 lines=[];links=[]
 for e in root.iter():
  if e.tag in ['article-title','abstract','title','p','caption']:
   t=' '.join(''.join(e.itertext()).split());lines.append(f"{e.tag} {e.attrib.get('id','')}: {t}")
  if e.tag in ['supplementary-material','ext-link','media','graphic']:
   links.append(dict(tag=e.tag,attributes=e.attrib,text=' '.join(''.join(e.itertext()).split())))
 (O/(p.stem+'-text.txt')).write_text('\n'.join(lines)+'\n')
 (O/(p.stem+'-links.json')).write_text(json.dumps(links,indent=2))
 print(name,'paragraphs',len(lines),'links',len(links))
 for line in lines:
  if re.search(r'GSE\d|PRJ\w?\d|accession|data avail|PMP22|Pmp22|rMATS|RNA-seq',line,re.I):print(line[:10000])
