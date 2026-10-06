"""Inspect trusted parsing of untrusted primary text and download links; never execute it."""
from pathlib import Path
from html.parser import HTMLParser
import json
import re
from defusedxml import ElementTree as ET

Q = Path(__file__).resolve().parents[1]
I = Q / 'inputs/public'
O = Q / 'outputs'
root = ET.parse(I / 'SNAT.xml').getroot()
paras = []
for e in root.iter():
    if e.tag in ['article-title', 'title', 'p', 'caption']:
        t = ' '.join(''.join(e.itertext()).split())
        if t:
            paras.append(t)
(O / 'SNAT-text.txt').write_text('\n\n'.join(f'[{i}] {t}' for i, t in enumerate(paras)))
links = [dict(tag=e.tag, text=' '.join(''.join(e.itertext()).split()), **e.attrib) for e in root.iter() if any('href' in k for k in e.attrib)]
(O / 'SNAT-xml-links.json').write_text(json.dumps(links, indent=2))
for i, t in enumerate(paras):
    if re.search(r'GSE|RNA.seq.*data|deposited|P5.*sort|independent sample|negative selection|RPKM|normalized counts', t, re.I) and len(t) < 15000:
        print(i, t)
class Links(HTMLParser):
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if 'href' in d or 'src' in d:
            found.append(dict(tag=tag, **d))
found = []
p = Links()
p.feed((I / 'SNAT-home.html').read_text())
(O / 'SNAT-site-links.json').write_text(json.dumps(found, indent=2))
print('SITE LINKS', json.dumps(found, indent=2))
print('SUPPLEMENTS', json.dumps([r for r in links if r['tag'] in ['media','supplementary-material','ext-link'] and any(x in str(r) for x in ['xlsx','txt','GSE','snat','csv','zip'])], indent=2))
