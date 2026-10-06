"""Render primary atlas filtering and bounded novelty-search metadata."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET
q = Path(__file__).resolve().parents[1]
s = q / 'inputs/sources'
root = ET.parse(s / 'polyasite-primary-bioc.source').getroot()
text = '\n\n'.join(p.findtext('text','') for p in root.findall('.//passage'))
(s / 'polyasite-primary-bioc.txt').write_text(text)
for p in text.split('\n\n'):
    if any(k in p.lower() for k in ['priming','cluster','normalized','threshold']):
        print('ATLAS',p)
x = json.loads((s/'novelty-ends-query-all.source').read_text())
assert len(x['resultList']['result']) == x['hitCount']
for r in x['resultList']['result']:
    print('NOVELTY',r['id'],r.get('pmcid'),r.get('title','[title absent in returned record]'))
