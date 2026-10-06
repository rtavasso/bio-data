"""Read source metadata and primary XML without executing content."""
import json
import sys
from pathlib import Path
from defusedxml import ElementTree as ET

for arg in sys.argv[1:]:
    p = Path(arg)
    print('\nSOURCE', p)
    if p.suffix == '.soft':
        block = []
        for line in p.read_text().splitlines():
            if line.startswith('^') or (line.startswith('!') and any(x in line.lower() for x in ['title', 'summary', 'overall_design', 'pubmed_id', 'supplementary_file', 'source_name', 'characteristics', 'treatment_protocol', 'growth_protocol', 'extract_protocol', 'description', 'data_processing', 'library_strategy'])):
                block.append(line)
        out = p.with_suffix('.metadata.txt')
        out.write_text('\n'.join(block) + '\n')
        print(out, len(block), 'lines')
    elif p.suffix == '.xml':
        root = ET.fromstring(p.read_bytes())
        lines = []
        for node in root.iter():
            if node.tag in ('article-title', 'title', 'p', 'table-wrap', 'supplementary-material'):
                text = ' '.join(''.join(node.itertext()).split())
                lines.append(node.tag + ' ' + node.get('id','') + ' ' + text)
            if node.tag in ('ext-link','media'):
                lines.append('LINK ' + str(node.attrib))
        out = p.with_suffix('.text.txt')
        out.write_text('\n\n'.join(lines))
        print(out, len(lines), 'blocks')
    elif p.suffix == '.json':
        obj = json.loads(p.read_text())
        print('output', obj.get('path'), obj.get('output_blob'))
