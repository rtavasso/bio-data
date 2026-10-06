"""Read-only source context inspection, not an outcome analysis."""
import json, textwrap, xml.etree.ElementTree as ET
from pathlib import Path
P=Path(__file__).resolve().parents[1]
lines=[]
for pmc,terms in {
 'PMC7430845':['rn5','biological replicates','CPT-cAMP','biological replicate','million','pooled','Sprague','DESeq','threshold','clustered'],
 'PMC7145652':['TATA','C22','seven','7 days','6–10'],
 'PMC6482019':['five putative','ENSMUST','mm10','mm9','four independent']}.items():
 t=ET.parse(P/'sources/primary'/f'{pmc}.xml')
 for e in t.iter('p'):
  txt=''.join(e.itertext())
  if any(s.lower() in txt.lower() for s in terms):
   lines += [pmc+' '+e.attrib.get('id',''),textwrap.fill(txt,120),'']
d=json.loads((P/'sources/GSE139321-metadata.json').read_text())
lines += ['GEO STRUCTURE',json.dumps(d,indent=2)]
(P/'sources/context-inspection.txt').write_text('\n'.join(lines))
print('saved context-inspection.txt')
