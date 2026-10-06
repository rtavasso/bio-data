"""Inspect primary-paper prose only; do not retrieve or analyze assay tables."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET

q = Path(__file__).resolve().parents[1]
label = 'nrg1-pum-bruchase-paper-r001'
receipt = json.loads((q / 'inputs/http' / (label + '.receipt.json')).read_text())
assert receipt['status'] == 200 and receipt['complete']
root = ET.parse(q / 'inputs/http' / (label + '.payload')).getroot()
lines = []
for element in root.iter():
    if element.tag in {'article-title', 'title', 'p', 'supplementary-material'}:
        text = ' '.join(''.join(element.itertext()).split())
        lines.append(text)
        if any(term.lower() in text.lower() for term in ['GSE145237', '30 min', '6 h', 'four biological', '48 h', 'absolute decay', 'model_coefficients', 'GEO', 'PRJNA']):
            print(text)
    if element.tag in {'media', 'ext-link'}:
        link = element.attrib.get('{http://www.w3.org/1999/xlink}href', '')
        if 'coefficients' in link or 'GSE' in link:
            print('NATIVE_LINK', link)
(q / 'inputs/views' / (label + '.txt')).write_text('\n'.join(lines))
