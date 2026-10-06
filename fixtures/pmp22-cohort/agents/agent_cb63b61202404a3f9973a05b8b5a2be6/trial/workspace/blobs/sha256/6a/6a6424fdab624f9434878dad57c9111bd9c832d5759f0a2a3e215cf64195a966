import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_90f4fed27b7e4793'
p = q / 'inputs/public'
lines=[]
for path in sorted(p.glob('search-*.json')):
    if path.name.endswith('-receipt.json'): continue
    d=json.loads(path.read_text())
    lines.append(f"SEARCH {path.name} hitCount={d['hitCount']} returned={len(d['resultList']['result'])}")
    for r in d['resultList']['result']:
        lines.append(f"{r.get('id')} {r.get('pmcid')} {r.get('firstPublicationDate')} {r.get('title')}")
        if path.name in {'search-nae1-nrf2-schwann.json','search-lxr-title.json'} or re.search(r'neddyl|MLN4924|Nrf2.*defici|Schwann',r.get('title',''),re.I):
            lines.append(r.get('abstractText','NO ABSTRACT'))
(p / 'search-screen.txt').write_text('\n'.join(lines))
for pmc in ['PMC11014456','PMC5802790','PMC12596376']:
    root=ET.parse(p/(pmc+'.xml')).getroot()
    print(pmc, 'IDS',[(e.attrib,''.join(e.itertext())) for e in root.findall('./front/article-meta/article-id')])
    for e in root.findall('.//ref'):
        txt=' '.join(e.itertext())
        if re.search(r'Nrf2|nuclear factor|proteasome|antioxidant',txt,re.I):print(e.get('id'),txt)
    for e in root.findall('.//supplementary-material'):
        print('SUPPLEMENT',ET.tostring(e,encoding='unicode'))
