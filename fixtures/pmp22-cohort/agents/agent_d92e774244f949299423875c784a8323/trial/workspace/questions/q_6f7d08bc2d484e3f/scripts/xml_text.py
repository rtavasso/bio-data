"""Read JATS/BioC data as text, preserving element locators. No execution."""
from pathlib import Path
import sys
from defusedxml import ElementTree as ET

for arg in sys.argv[1:]:
    path = Path(arg)
    root = ET.fromstring(path.read_bytes())
    out = []
    for i, el in enumerate(root.iter()):
        if el.tag in {'article-title', 'title', 'p', 'table', 'caption', 'ext-link', 'supplementary-material', 'text'}:
            text = ' '.join(' '.join(el.itertext()).split())
            if text:
                out.append(f'[{el.tag} {el.get("id", "")} element={i}] {text}')
        if el.tag in {'graphic','media','ext-link','supplementary-material'}:
            out.append(f'[link element={i}] {el.attrib}')
    target = Path(__file__).resolve().parents[1] / 'inputs/text' / (path.name + '.txt')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('\n\n'.join(out) + '\n')
    print(target)
