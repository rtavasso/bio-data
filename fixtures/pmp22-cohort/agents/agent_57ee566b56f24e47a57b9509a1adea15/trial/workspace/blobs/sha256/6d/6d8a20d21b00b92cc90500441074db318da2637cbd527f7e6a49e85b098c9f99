"""Print newly relevant early-injury study titles and array scale-source passages."""
import json,os,re
from pathlib import Path
from defusedxml import ElementTree as ET
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
ids=json.loads((q/'outputs/discovery-early-injury.json').read_text()).get('resources',[])
allrows=json.loads((q/'outputs/discovery-titles.json').read_text())
for r in allrows:
    if r['subject'] in ids:print(r['pmid'],r['pmcid'],r['title'])
root=ET.parse(q/'inputs/primary/PMC9469140.xml').getroot()
for i,p in enumerate(root.iter('p')):
    text=' '.join(p.itertext())
    if re.search(r'log2|logarithm|microarray analysis|GeneSpring|normalized|normalised',text,re.I):print('ETV1',i,text[:3000])
