"""Read primary mTORC1 design/novelty paragraphs and exact stable-ID mappings."""
import json,os,re
from pathlib import Path
from defusedxml import ElementTree as ET
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
root=ET.parse(q/'inputs/public/PMC5956991.xml').getroot();rows=[]
for i,p in enumerate(root.iter('p')):
    s=' '.join(p.itertext())
    if re.search(r'RNA.sequenc|RNA.seq|contralateral|Pmp22|PMP22|postnatal day|P60|paired',s,re.I):
        rows.append({'paragraph':i,'text':s});print(i,s[:4200])
(q/'outputs/raptor-primary-design.json').write_text(json.dumps(rows,indent=2))
for p in sorted((q/'inputs/public').glob('ensembl-mouse-*.json')):
    if '.receipt.' in p.name:continue
    x=json.loads(p.read_text());print('SYMBOL_MAP',x['display_name'],x['id'],x['assembly_name'])
