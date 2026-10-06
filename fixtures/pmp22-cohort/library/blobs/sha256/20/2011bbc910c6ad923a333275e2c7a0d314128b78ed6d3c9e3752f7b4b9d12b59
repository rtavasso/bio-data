import json
import re
import sys
from pathlib import Path
from defusedxml import ElementTree as ET

rootdir=Path(__file__).resolve().parents[1]
for name in sys.argv[1:]:
    p=rootdir/'inputs'/'sources'/name
    root=ET.parse(p).getroot()
    pars=[]
    for i,e in enumerate(root.iter('p'),1):
        text=' '.join(''.join(e.itertext()).split())
        if re.search(r'GSE\d|PMP22|biological replic|RNA.seq librar|ribosome profiling was|ribo.spike was|DESeq|reads were|poly.?A|data availability',text,re.I):
            pars.append({'paragraph':i,'id':e.get('id'),'text':text})
    supp=[]
    for e in root.iter():
        if e.tag in ['supplementary-material','ext-link','media']:
            href=e.get('{http://www.w3.org/1999/xlink}href')
            if href:
                supp.append({'tag':e.tag,'href':href,'text':' '.join(''.join(e.itertext()).split())[:300]})
    obj={'source':name,'paragraphs':pars,'links':supp}
    (rootdir/'outputs'/(name+'.design.json')).write_text(json.dumps(obj,indent=2)+'\n')
    for x in pars:
        print(x['paragraph'],x['id'],x['text'][:3500])
    print('LINKS',json.dumps(supp))
