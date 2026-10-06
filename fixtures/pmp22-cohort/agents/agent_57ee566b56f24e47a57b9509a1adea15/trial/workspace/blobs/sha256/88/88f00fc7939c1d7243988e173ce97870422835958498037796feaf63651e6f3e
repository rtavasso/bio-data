import json
import os
from pathlib import Path
from defusedxml import ElementTree as ET
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
for name in ['nae1','repair']:
    root=ET.parse(q/f'inputs/public/{name}.xml').getroot()
    paras=[]
    for el in root.iter():
        if el.tag in ['p','title']:
            paras.append(' '.join(el.itertext()))
    (q/f'outputs/{name}-paragraphs.txt').write_text('\n\n'.join(paras))
    print(name)
    for i,p in enumerate(paras):
        terms=['nrf2','nqo1','hmox1','pmp22','purif','p0cre','p0-cre','cre','culture','macrophage','p7','postnatal','pool']
        if any(t in p.lower() for t in terms):
            print(i,p[:4000])
obj=json.loads((q/'inputs/public/matched-neonatal-discovery.json').read_text())
rows=[{k:r.get(k) for k in ['id','pmcid','title','pubYear','abstractText']} for r in obj['resultList']['result']]
(q/'outputs/matched-neonatal-titles.json').write_text(json.dumps({'hitCount':obj['hitCount'],'returned':rows},indent=2))
print('MATCHED',obj['hitCount'])
for row in rows:
    print(row['id'],row['pmcid'],row['title'])
