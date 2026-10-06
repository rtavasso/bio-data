"""Render BioC source passages and inspect primary-source locators without execution."""
from pathlib import Path
from xml.etree import ElementTree as ET

q = Path(__file__).resolve().parents[1]
for p in (q / 'inputs' / 'primary').glob('*-bioc.source'):
    root = ET.fromstring(p.read_bytes())
    parts = []
    for e in root.findall('.//passage'):
        meta = {i.get('key'): i.text for i in e.findall('infon')}
        parts.append('[' + str(meta) + ' offset=' + str(e.findtext('offset')) + ']\n' + str(e.findtext('text')))
    p.with_suffix('.txt').write_text('\n\n'.join(parts))
    print(p.name, 'passages', len(parts), 'first', parts[:2])
for name in ['PMC13431160', 'PMC9852534', 'PMC3002990', 'PMC11784151']:
    root = ET.fromstring((q / 'inputs' / 'primary' / (name + '.source')).read_bytes())
    print(name, 'TITLE', root.findtext('.//article-title'))
    if name == 'PMC13431160':
        for e in root.iter('p'):
            t = ' '.join(''.join(e.itertext()).split())
            if any(k in t for k in ['GSE', 'SLAM', 'degradation rate', 'PMP22', 'Pmp22', '4sU', 'half-life']):
                print(t)
