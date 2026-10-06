"""Inspect inherited lipid evidence and local source representations; no scientific rerun."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import zipfile

q = Path(__file__).resolve().parents[1]
root = q.parents[2]
old = q.parent / 'q_277f20df4b6b47cc'
inputs = q / 'inputs'
inputs.mkdir(exist_ok=True)


def call(args, name):
    p = subprocess.run([str(root / 'bin/bio'), *args], capture_output=True, text=True)
    (inputs / (name + '.json')).write_text(p.stdout)
    (inputs / (name + '.stderr.txt')).write_text(p.stderr)
    assert p.returncode == 0, (name, p.returncode)
    return json.loads(p.stdout)


aid = 'artifact_fe204b5545a6f3da42b0147511661caa5b1a4398f1dc1c7cb07ba45fbf47e703'
assert re.fullmatch(r'artifact_[0-9a-f]{64}', aid)
d = call(['artifact', 'show', aid], 'original-lipid-artifact')
print('ORIGINAL ARTIFACT', json.dumps({k: d['manifest'][k] for k in ['title', 'output', 'derivation']}, indent=2))
call(['community', 'show', 'post_a37ef5629cc842b39412d0876de9172b'], 'request')
peer = call(['community', 'show', 'post_78aab10c0b084ef89511249f43fe0180'], 'peer-publication')
call(['community', 'show', 'post_07972ef0c59c40b293bf399eac5f429d'], 'peer-answer')
call(['community', 'show', 'post_97e94eb0330e4fd98cae464ac8919fbb'], 'peer-review')
call(['community', 'agents'], 'agents')
for term in ['ABCA1', 'FDFT1', 'LXR', 'EndoH', 'cholesterol efflux']:
    call(['community', 'search', '--text', term, '--limit', '30'], 'search-' + term.replace(' ', '-'))


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


for rel in ['inputs/continuation/PMC6607759.html', 'inputs/upstream/PMC6623163.html',
            'inputs/upstream/PMC6623163.xml', 'inputs/upstream/PMC6623163-biocc.json']:
    p = old / rel
    raw = p.read_bytes()
    print('\nSOURCE', rel, 'bytes', len(raw), 'sha256', hashlib.sha256(raw).hexdigest())
    text = raw.decode()
    if p.suffix == '.html':
        parser = Text()
        parser.feed(text)
        text = '\n'.join(parser.parts)
        print(text[:1800])
        print('HEADINGS', re.findall(r'<h[12][^>]*>(.*?)</h[12]>', raw.decode(), re.S)[:12])
    elif 'biocc' in p.name:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            print('NON-JSON RESPONSE', text[:1800])
            value = None
        if isinstance(value, list):
            for collection in value:
                for doc in collection.get('documents', []):
                    passages = doc.get('passages', [])
                    print('BIOC', doc.get('id'), 'passages', len(passages), 'section-types', sorted({p.get('infons', {}).get('section_type', '') for p in passages}))
                    for paragraph in passages:
                        if paragraph.get('infons', {}).get('type') == 'title' or re.search(r'PMP22|Pmp22|pmp22', paragraph.get('text', '')):
                            print(json.dumps(paragraph, ensure_ascii=False))
        elif value is not None:
            print(text[:1800])
    else:
        print(text[:1800])
# Native ZIP inspection reads directory entries only; no extraction or execution.
p = old / 'inputs/upstream/FDFT1-supplements.zip'
print('\nFDFT1 ZIP bytes', p.stat().st_size, 'sha256', hashlib.sha256(p.read_bytes()).hexdigest())
with zipfile.ZipFile(p) as archive:
    for member in archive.infolist():
        if member.filename.lower().endswith(('.zip', '.docx')):
            print('SELECTABLE MEMBER', member.filename, member.file_size, member.compress_size)
print('FDFT1 OLD INVENTORY', (old / 'outputs/upstream/FDFT1-data-inventory.json').read_text())
# Only non-sensitive receipt fields; do not expose headers/cookies.
allowed = {'url', 'final_url', 'path', 'status', 'http_status', 'bytes', 'sha256', 'error', 'content_type', 'started', 'finished', 'outcome'}
for name in ['PMC6623163.html.json', 'PMC6623163.xml.json', 'PMC6623163-biocc.json.json', 'FDFT1-supplements.zip.json']:
    d = json.loads((old / 'inputs/upstream/receipts' / name).read_text())
    print('RECEIPT', name, json.dumps({k: v for k, v in d.items() if k in allowed}, ensure_ascii=False))
transport = json.loads((old / 'inputs/continuation/transport.json').read_text())
for i, entry in enumerate(transport['entries']):
    if entry.get('path') == 'inputs/continuation/PMC6607759.html':
        print('CONTINUATION RECEIPT', i, json.dumps({k: v for k, v in entry.items() if k in allowed}))
