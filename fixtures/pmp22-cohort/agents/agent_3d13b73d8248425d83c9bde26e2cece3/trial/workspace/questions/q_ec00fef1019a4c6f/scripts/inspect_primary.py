import json
import os
from pathlib import Path
from defusedxml import ElementTree as ET
q = Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
for name in ['nae1-paper','repair-paper','nae1-discovery','matched-discovery']:
    obj=json.loads((q/f'inputs/public/{name}.json').read_text())
    rows=[{k:r.get(k) for k in ['id','pmcid','title','pubYear','authorString']} for r in obj['resultList']['result']]
    (q/f'outputs/{name}-titles.json').write_text(json.dumps({'hitCount':obj['hitCount'],'returned':rows},indent=2))
    print(name,obj['hitCount'])
    for row in rows:
        print(row['id'],row['pmcid'],row['title'])
root=ET.parse(q/'inputs/public/snat.xml').getroot()
paras=[' '.join(el.itertext()) for el in root.iter() if el.tag in ['p','title']]
(q/'outputs/snat-paragraphs.txt').write_text('\n\n'.join(paras))
for i,p in enumerate(paras):
    if any(t in p.lower() for t in ['deplet','independent biological','subject','four biological','sorted','facs']):
        print('SNAT',i,p[:2200])
