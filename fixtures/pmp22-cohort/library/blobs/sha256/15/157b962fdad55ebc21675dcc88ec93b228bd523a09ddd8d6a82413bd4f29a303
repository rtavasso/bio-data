"""Inspect saved primary sources and imported artifact bytes; never run imported code."""
import csv
import gzip
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import textwrap
import zipfile
from pathlib import Path
from html.parser import HTMLParser

Q = Path(__file__).resolve().parents[1]
PRIOR = Q.parent / 'q_e9e29d6eed344964'
S = Q / 'sources'
(S / 'inputs').mkdir(parents=True, exist_ok=True)
A = {
    'native': 'artifact_d83da7f82f8d73dd56ca563f47ac35fc5724bc0d4eba21c46456f6105f3dfa78',
    'bundle': 'artifact_306fb5726176ef0cce72cbb8e050d575baedd023b6014e8fe674336b16a4c606',
    'locator': 'artifact_9f094b4877fb0839665160ea6f0ea9811ad84043225962a91a96cbc33dcd1303',
    'mapping': 'artifact_46c490850c14f6afe9d32cb74b32ad94e60d828de0751236d25c51fcc079771a',
    'samples': 'artifact_67bf3bc306dd377f7e63f8df1b8c936998f5dc6a6d5682e9a9f0493de4b2387d',
}

def run(*args):
    result = subprocess.run(['./bin/bio', *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)

manifests = {}
for key, aid in A.items():
    info = run('artifact', 'show', aid)
    raw = Path(info['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == info['output_blob']
    (S / f'{key}-artifact.json').write_text(json.dumps(info, indent=2))
    dest = S / 'inputs' / info['manifest']['output']['name']
    dest.write_bytes(raw)
    manifests[key] = {'artifact': aid, 'sha256': info['output_blob'], 'bytes': len(raw), 'path': str(dest.relative_to(Q))}
    print('VERIFIED', key, info['output_blob'], len(raw), dest.name)

class StaticText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        if tag in ('p', 'h1', 'h2', 'h3', 'h4', 'li', 'tr', 'section'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip -= 1
        if tag in ('p', 'h1', 'h2', 'h3', 'h4', 'li', 'tr'):
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

with zipfile.ZipFile(Q / manifests['bundle']['path']) as archive:
    assert archive.testzip() is None
    for name in archive.namelist():
        if name.startswith('sources/') and name.endswith(('.html', '.txt', '.gz')):
            dest = S / 'inputs' / Path(name).name
            data = archive.read(name)
            if dest.exists():
                assert dest.read_bytes() == data
            else:
                dest.write_bytes(data)
            print('MEMBER', name, len(data), hashlib.sha256(data).hexdigest())
            if name.endswith('.html'):
                parser = StaticText()
                parser.feed(data.decode())
                plain = '\n'.join(textwrap.fill(re.sub(r'\s+', ' ', s).strip(), 140) for s in ''.join(parser.parts).split('\n') if s.strip())
                (S / f'{dest.stem}.txt').write_text(plain)
            if name.endswith('.txt.gz'):
                assert gzip.decompress(data) == (Q / manifests['native']['path']).read_bytes()

for name in ['PMC7430845.txt', 'PMC3100536.txt', 'rn5-Pmp22-promoter-sequence.json', 'rn5-refGene-Pmp22.json']:
    raw = (PRIOR / 'sources/primary' / name).read_bytes()
    dest = S / 'inputs' / name
    dest.write_bytes(raw)
    manifests[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'path': str(dest.relative_to(Q)), 'origin': 'inherited primary file; no new HTTP claim'}
    if name.endswith('.txt'):
        (S / name).write_text('\n'.join(textwrap.fill(line, 140) for line in raw.decode().splitlines()))

native = Q / manifests['native']['path']
with native.open() as handle:
    reader = csv.DictReader(handle, delimiter='\t')
    fields = reader.fieldnames
    rows = list(reader)
print('HEADERS', json.dumps(fields))
print('ROWS', len(rows))
(Q / 'sources/immutable-inputs.json').write_text(json.dumps(manifests, indent=2))
print('PACKAGES', {m: importlib.util.find_spec(m) is not None for m in ['pandas', 'numpy', 'matplotlib', 'scipy']})
print('DISK_FREE', shutil.disk_usage(Q).free)

# Full current bodies of relevant non-seed posts and replies, plus snapshots of proposals.
for post in ['post_b98abec27d324242816b110d7726fd77', 'post_ecc13cabecf54b789e538f695e4bdca2', 'post_8361a97308264d1892df187d5132826d', 'post_7b25ba716a574ea9b8e4c87889e8ff85', 'post_3bff97ec053840c283a34e42a1769eeb']:
    data = run('community', 'show', post)
    (S / 'community' / f'{post}.json').write_text(json.dumps(data, indent=2))
    (S / 'community' / f'{post}.md').write_text(data['content']['body'])
    print('CURRENT_POST', post, 'REPLIES', data.get('replies'), 'SUPERSEDED', data.get('superseded_by'))
