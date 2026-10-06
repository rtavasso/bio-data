"""Compact exact catalog inventories, primary links, and reference metadata only."""
from pathlib import Path
import json
import re
from defusedxml import ElementTree as ET
Q = Path(__file__).resolve().parents[1]
for f in ['inputs/inventory-GSE138577.json', 'inputs/resolve-GSE137870.json']:
    d = json.loads((Q/f).read_text())
    print(f, json.dumps(d, indent=2)[:25000])
r = ET.parse(Q/'inputs/public/SNAT.xml').getroot()
for e in r.iter():
    if e.tag in ['supplementary-material','media']:
        print('SUPP', e.tag, e.attrib, ''.join(e.itertext())[:350])
r = ET.parse(Q/'inputs/public/SEMA3B.xml').getroot()
print('SEMA3B TITLE', r.findtext('.//article-title'))
for e in r.iter('p'):
    t = ' '.join(''.join(e.itertext()).split())
    if re.search(r'GSE177037|RNA.seq|immunopanning|10.20|P18|18.day',t,re.I):
        print('REPAIR',t)
d=json.loads((Q/'outputs/inherited-evidence-package.json').read_text())
print('PACKAGE KEYS', list(d))
# Show entries whose names identify useful matrices without reading numeric outcomes.
def walk(x):
    if isinstance(x,dict):
        if any(re.search(r'nae1-all|figlia.*native|source-counts|shared-effects|Figlia-extraction',str(v),re.I) for v in x.values() if isinstance(v,str)):
            print('PACKAGE MATRIX',json.dumps(x)[:900])
        for v in x.values():
            walk(v)
    elif isinstance(x,list):
        for v in x:
            walk(v)
walk(d)
# Keep metadata only from GEO family response; source table values not exposed.
lines = (Q/'inputs/public/GSE147285-family.soft').read_text().splitlines()
sel = [s for s in lines if s.startswith(('^SAMPLE', '!Sample_title', '!Sample_characteristics', '!Sample_extract_protocol', '!Sample_data_processing', '!Sample_supplementary_file'))]
(Q/'outputs/GSE147285-metadata.txt').write_text('\n'.join(sel))
print('TOMA', '\n'.join(sel)[:12000])
