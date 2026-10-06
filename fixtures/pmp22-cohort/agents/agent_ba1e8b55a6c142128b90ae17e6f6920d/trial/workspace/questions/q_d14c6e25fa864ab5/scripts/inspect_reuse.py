"""Inspect preserved local artifacts; extract selected data only, no imported execution."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
inputs = q / 'inputs'
inputs.mkdir(exist_ok=True)
for name in ['prior-package', 'redox']:
    a = json.loads((q / 'outputs' / f'{name}-artifact.json').read_text())
    h = a['output_blob']
    p = w / 'blobs/sha256' / h[:2] / h
    assert hashlib.sha256(p.read_bytes()).hexdigest() == h
    data = json.loads(p.read_text())
    (q / 'outputs' / f'{name}-readable.json').write_text(json.dumps(data, indent=2))
    print(name, 'output', h, 'keys', list(data))
    if name == 'redox':
        for item in a['manifest']['derivation']['inputs']:
            old = item.get('selector', {}).get('path_at_execution', '')
            if 'PMC5802790' not in old:
                continue
            h = item['blob']
            p = w / 'blobs/sha256' / h[:2] / h
            b = p.read_bytes()
            assert hashlib.sha256(b).hexdigest() == h
            dest = inputs / Path(old).name
            dest.write_bytes(b)
            print('SELECTED INHERITED', dest.name, h)
            if dest.suffix == '.xml':
                root = ET.fromstring(b)
                lines = []
                for elem in root.iter():
                    if elem.tag in ('p', 'title', 'caption'):
                        text = ' '.join(''.join(elem.itertext()).split())
                        lines.append(f'{elem.tag} id={elem.get("id", "")} | {text}')
                (q / 'outputs' / 'PMC5802790-readable.txt').write_text('\n'.join(lines))
