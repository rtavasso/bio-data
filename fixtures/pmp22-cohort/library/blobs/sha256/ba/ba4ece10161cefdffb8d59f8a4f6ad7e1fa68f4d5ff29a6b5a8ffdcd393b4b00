"""Make inspection-friendly source views, retaining unchanged downloaded inputs."""
from collections import Counter
import json
from pathlib import Path
from xml.etree import ElementTree as ET
q=Path(__file__).resolve().parents[1]
o=q/'inputs/views'
o.mkdir(exist_ok=True)
for label in ['batch-example-file-meta-r001','eclip-example-file-meta-r001','batch-document-meta-r001']:
    obj=json.loads((q/'inputs/http'/(label+'.payload')).read_text())
    (o/(label+'.json')).write_text(json.dumps(obj,indent=2))
    print(label, json.dumps({k:obj.get(k) for k in ['accession','file_format','file_format_type','output_type','assembly','genome_annotation','submitted_file_name','file_size','href','dataset','attachment','description']},indent=2))
r=ET.parse(q/'inputs/http/encore-paper-xml-r001.payload').getroot()
lines=[]
for e in r.iter():
    if e.tag in ['p','title','table-wrap','supplementary-material']:
        text=' '.join(''.join(e.itertext()).split())
        lines.append(f"{e.tag} {e.get('id','')}: {text}")
    if e.tag in ['ext-link','media']:
        print('SOURCE LINK',e.attrib, ''.join(e.itertext())[:100])
(o/'paper.txt').write_text('\n'.join(lines))
obj=json.loads((q/'inputs/http/encode-released-eclip-files-r001.payload').read_text())
print('ECLIP COUNTS',obj.get('total'),len(obj.get('@graph',[])),Counter((f.get('output_type'),f.get('assembly')) for f in obj.get('@graph',[])))
print('ECLIP FIRST',json.dumps(obj.get('@graph',[])[:1],indent=2)[:6000])
