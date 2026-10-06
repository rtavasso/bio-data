from defusedxml import ElementTree as ET
import pathlib,json
q=pathlib.Path(__file__).resolve().parents[1]; out=q/'outputs/source-text';out.mkdir(exist_ok=True)
for p in (q/'inputs/continuation').glob('PMC*.xml'):
 try:root=ET.parse(p).getroot()
 except Exception:continue
 rows=[]
 for i,e in enumerate(root.iter()):
  if e.tag in ['article-title','abstract','sec','fig','table-wrap','supplementary-material']:
   if e.tag=='sec':
    title=e.find('title');t=''.join(title.itertext()) if title is not None else ''
    for j,x in enumerate(e):
     if x.tag in ('p','title'):rows.append(f'{e.tag} id={e.get("id")} / {t} / child {j}: '+''.join(x.itertext()))
   elif e.tag!='abstract':rows.append(f'{e.tag} id={e.get("id")}: '+''.join(e.itertext()))
 (out/(p.stem+'.txt')).write_text('\n\n'.join(rows))
 supp=[]
 for e in root.iter():
  if e.tag in ['ext-link','media','supplementary-material','graphic']:
   supp.append({'tag':e.tag,'attrib':e.attrib,'text':''.join(e.itertext())[:300]})
 (out/(p.stem+'-links.json')).write_text(json.dumps(supp,indent=2))
 print(p.stem,'textchars',sum(map(len,rows)),'links',len(supp))
