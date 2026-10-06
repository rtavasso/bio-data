"""Read JATS XML as text only; never execute embedded source content."""
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

source, dest = map(Path, sys.argv[1:3])
root = ET.fromstring(source.read_bytes())
lines = []
for node in root.iter():
    if node.tag in {'article-title', 'title', 'p', 'fig', 'table-wrap', 'supplementary-material'}:
        text = ' '.join(''.join(node.itertext()).split())
        lines.append(f"[{node.tag} id={node.get('id', '')}] {text}")
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text('\n\n'.join(lines) + '\n')
links = []
for node in root.iter():
    for key, value in node.attrib.items():
        if key.endswith('href'):
            links.append({'tag': node.tag, 'id': node.get('id'), 'href': value})
dest.with_suffix('.links.json').write_text(json.dumps(links, indent=2, allow_nan=False) + '\n')
print(json.dumps({'source': str(source), 'text': str(dest), 'records': len(lines), 'links': len(links)}))
