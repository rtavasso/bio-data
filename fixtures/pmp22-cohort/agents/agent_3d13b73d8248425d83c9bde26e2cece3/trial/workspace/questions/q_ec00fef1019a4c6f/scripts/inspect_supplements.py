import json
import os
from pathlib import Path
from defusedxml import ElementTree as ET
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
for name in ['repair','nae1']:
    root=ET.parse(q/f'inputs/public/{name}.xml').getroot()
    for el in root.iter():
        if el.tag in ['supplementary-material','media','ext-link']:
            txt=' '.join(el.itertext())
            if el.tag!='ext-link' or any(x in txt.lower() for x in ['data','geo']):
                print(name,el.tag,el.attrib,txt[:800])
obj=json.loads((q/'inputs/public/nae1-discovery.json').read_text())
for r in obj['resultList']['result']:
    if r.get('id')=='40659529':
        (q/'outputs/nmj-candidate.json').write_text(json.dumps(r,indent=2))
        print('NMJ ABSTRACT',r.get('abstractText'),r.get('doi'))
