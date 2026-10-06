"""Inspect exact high-temporal study methods and BioStudies direct-file routing."""
import json,os
from pathlib import Path
from defusedxml import ElementTree as ET
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
root=ET.parse(q/'inputs/public/PMC5405595.xml').getroot()
for i,p in enumerate(root.iter('p')):
    if i<13:print(i,' '.join(p.itertext()))
for el in root.iter('supplementary-material'):print('SUPPLEMENT',' '.join(el.itertext()),[(c.tag,c.attrib) for c in el])
x=json.loads((q/'inputs/public/E-MEXP-3491.biostudies.json').read_text());print('TOP_ATTRIBUTES',x['attributes'])
