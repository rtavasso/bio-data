"""Inspect file identity, source headers and existing peer evidence only; no analysis rerun."""
import hashlib
import json
from pathlib import Path
from html.parser import HTMLParser

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
old = w / 'questions/q_277f20df4b6b47cc'


class Titles(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.parts = []
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag in ('title', 'h1', 'h2'):
            self.active = tag
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.active:
            self.values.append([tag, ' '.join(' '.join(self.parts).split())])
            self.active = None


for pmc in ('PMC3298281', 'PMC7322568', 'PMC5181599'):
    p = old / 'inputs/continuation' / (pmc + '.html')
    raw = p.read_bytes()
    parser = Titles()
    parser.feed(raw.decode())
    print(pmc, len(raw), hashlib.sha256(raw).hexdigest(), parser.values)
profile = json.loads((q / 'inputs/tss-native-profile.json').read_text())
for p in profile['profiles']:
    print('PROFILE', p.keys(), json.dumps({k: v for k, v in p['facts'].items()
          if k != 'related_source_context'}, indent=2))
print('TOP LEVEL', {k: v for k, v in profile.items() if k != 'profiles'})
peer = json.loads((q / 'inputs/peer-mapping-artifact.json').read_text())
h = peer['output_blob']
data = (w / 'blobs/sha256' / h[:2] / h).read_bytes()
assert hashlib.sha256(data).hexdigest() == h
print('PEER MAPPING:', data.decode())
print('PEER PUBLICATION:', json.loads((q / 'inputs/peer-publication.json').read_text())['content']['body'])
print('INHERITED TSS MANIFEST:', json.dumps(json.loads((q / 'inputs/inherited-tss-artifact.json').read_text())['manifest'], indent=2))
for h in ('658dbed20a15422a2f536ce791e29ed2b11776a72de579cf4aa3358aead71696',
          '31a6d5ee7e0ce9a436e3efbff1e6f944951d363d729de24ed52015bbff395c2a',
          '8aacf06456dddcff82f54db414a35a8f8808362e05e25bf9ff0bd7fcdb407dfa',
          'c2d953ef6d228d5bf81f39fd367f4594f09116f314dded54cc208dc82772a587'):
    text = (w / 'blobs/sha256' / h[:2] / h).read_text()
    print('6077802 SEARCH HIT', h, text[:250])
    if text.startswith('{'):
        d = json.loads(text)
        print('JSON KEYS', list(d))
    else:
        parser = Titles()
        parser.feed(text)
        print('TITLES', parser.values[:3])
