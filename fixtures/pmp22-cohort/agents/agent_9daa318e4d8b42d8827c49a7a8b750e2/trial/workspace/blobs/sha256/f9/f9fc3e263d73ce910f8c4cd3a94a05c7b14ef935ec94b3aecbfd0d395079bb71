"""Inspect locally preserved source metadata and paper passages, never execute source code."""
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from defusedxml import ElementTree as ET

q = Path(__file__).resolve().parents[1]
w = q.parents[1]
old = w / 'questions/q_277f20df4b6b47cc'


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks = []
        self.parts = None

    def handle_starttag(self, tag, attrs):
        if tag in {'p', 'h1', 'h2', 'h3', 'title'}:
            self.parts = []

    def handle_data(self, data):
        if self.parts is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag in {'p', 'h1', 'h2', 'h3', 'title'} and self.parts is not None:
            self.chunks.append(''.join(self.parts))
            self.parts = None


for name in ['PMC6416471.xml', 'PMC5730339.html']:
    p = old / 'inputs/iteration' / name
    if p.suffix == '.xml':
        tree = ET.parse(p)
        chunks = [''.join(e.itertext()) for e in tree.iter() if e.tag in {'p', 'article-title', 'title'}]
    else:
        parser = Paragraphs()
        parser.feed(p.read_text())
        chunks = parser.chunks
    print('\nPAPER', name, 'sha256', hashlib.sha256(p.read_bytes()).hexdigest())
    for i, paragraph in enumerate(chunks):
        if re.search(r'puromy|methion|35S|spike|protein synthesis|same sample|400.nM|200.nM|1.μM|1.µM|thapsigargin', paragraph, re.I):
            print('PASSAGE', i, paragraph)
for name in ['GSE118660.soft', 'GSE90070.soft']:
    p = old / 'inputs/iteration' / name
    print('\nSERIES', name)
    for line in p.read_text().splitlines():
        if re.match(r'!Series_(title|overall_design|summary|pubmed_id|supplementary_file)', line):
            print(line)
for name in ['GSE118660_MEF-counts.txt.gz', 'GSE118660_MEF-tpm.txt.gz',
             'GSE118660_3t3-TPM.txt.gz', 'GSE90070_dataCount.csv.gz']:
    p = old / 'inputs/iteration' / name
    with gzip.open(p, 'rt') as f:
        print('HEADER', name, f.readline().rstrip())
        print('FIRST ROW', f.readline().rstrip())
print('NIH COUNT HEADER')
h = '6f893c348e2297eb7bac49bf61c0cb6ab0dd3fcd512eb90124f7715a9fc77287'
p = w / 'blobs/sha256' / h[:2] / h
assert hashlib.sha256(p.read_bytes()).hexdigest() == h
with gzip.open(p, 'rt') as f:
    print(f.readline().rstrip())
    print(f.readline().rstrip())
print('PEER ELIGIBILITY')
print((q / 'outputs/peer-sample-eligibility.json').read_text())
# Do not expose response headers, which may contain session material.
for subdir in ['iteration', 'context-audit']:
    p = old / 'inputs' / subdir / 'transport.json'
    if not p.exists():
        continue
    records = json.loads(p.read_text())
    entries = records.get('entries', []) if isinstance(records, dict) else records
    print('TRANSPORT', subdir, 'entries', len(entries))
    for i, entry in enumerate(entries):
        if re.search(r'GSE118660|GSE90070|PMC6416471|PMC5730339|Gonen', json.dumps(entry)):
            print(i, json.dumps({k: entry[k] for k in ['path', 'url', 'status', 'bytes', 'sha256', 'error', 'accounting_note'] if k in entry}, ensure_ascii=False))
