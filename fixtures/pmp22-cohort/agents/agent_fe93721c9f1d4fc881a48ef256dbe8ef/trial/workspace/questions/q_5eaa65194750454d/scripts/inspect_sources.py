"""Readable source passages and compact manifest inspection; no downloaded code."""
import json
import re
import sys
from pathlib import Path
from defusedxml import ElementTree as ET

q = Path(__file__).resolve().parents[1]
if sys.argv[1] == 'xml':
    path, label = Path(sys.argv[2]), sys.argv[3]
    root = ET.fromstring(path.read_bytes())
    records = []
    for i, e in enumerate(root.iter()):
        if e.tag in ['article-title', 'p', 'table-wrap', 'fig', 'supplementary-material']:
            records.append({'element': i, 'tag': e.tag, 'id': e.get('id'), 'text': ' '.join(' '.join(e.itertext()).split())})
    (q / 'outputs' / (label + '.text.json')).write_text(json.dumps(records, indent=2) + '\n')
    for r in records:
        if re.search(r'GSE\d|RNA.seq|RNA sequencing|data avail|Krox20|Sox10|Egr2|supplementary file', r['text'], re.I) and len(r['text']) < 14000:
            print(json.dumps(r))
    print('LINKS', json.dumps([{k: v for k, v in e.attrib.items()} for e in root.iter() if any('href' in k for k in e.attrib)]))
else:
    d = json.loads(Path(sys.argv[2]).read_text())
    m = d['manifest']
    print(json.dumps({'artifact': d['id'], 'output': m['output'], 'inputs': m['derivation']['inputs'], 'parameters': m['derivation']['parameters']}, indent=2))
