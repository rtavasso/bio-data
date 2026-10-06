"""Render source paragraphs and discovery metadata, without executing sources."""
import json
from pathlib import Path
import re
import sys
import textwrap
from defusedxml import ElementTree as ET

Q = Path(__file__).resolve().parents[1]
for name in sys.argv[1:]:
    if name.endswith('.xml'):
        path = Q / 'inputs' / name
        root = ET.fromstring(path.read_bytes())
        lines = []
        for node in root.iter():
            if node.tag in ('article-title', 'title', 'p', 'table', 'supplementary-material'):
                text = ' '.join(''.join(node.itertext()).split())
                lines.append(f'[{node.tag} {node.attrib.get("id", "")}] ' + textwrap.fill(text, 120))
        text = '\n\n'.join(lines)
        (Q / 'outputs' / (name + '.txt')).write_text(text)
        links = [{'tag': n.tag, **n.attrib} for n in root.iter() if any('href' in k for k in n.attrib)]
        (Q / 'outputs' / (name + '.links.json')).write_text(json.dumps(links, indent=2))
        print(name, 'accessions', sorted(set(re.findall(r'GSE\d+|E-[A-Z]+-\d+|PXD\d+', text))))
        for line in lines:
            if any(k in line.lower() for k in ['data availability', 'accession', 'source data', 'rna-seq', 'transcriptom', 'lipidomic']):
                print(line[:700])
    else:
        doc = json.loads((Q / 'outputs' / name).read_text())
        print(name, json.dumps(doc, indent=2))
