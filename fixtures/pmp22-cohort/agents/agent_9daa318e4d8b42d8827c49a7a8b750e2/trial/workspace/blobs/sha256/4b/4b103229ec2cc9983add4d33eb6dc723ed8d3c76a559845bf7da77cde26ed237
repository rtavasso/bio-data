"""Read local inherited registration/source evidence without executing inherited code."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

Q = Path(__file__).resolve().parents[1]
P = Q.parent / 'q_277f20df4b6b47cc'
I = Q / 'inputs'
O = Q / 'outputs'

def save(p, x):
    p.write_text(json.dumps(x, indent=2, allow_nan=False) + '\n')

def cli(args, name):
    r = subprocess.run(['./bin/bio', *args], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    save(I / name, d)
    return d

records = []
for rel in ['outputs/upstream/rna-first-registration.json', 'outputs/upstream/final-registration.json', 'outputs/specific/registrations.json']:
    d = json.loads((P / rel).read_text())
    def walk(x):
        if isinstance(x, dict):
            if 'artifact' in x:
                records.append(dict(registry=rel, **x))
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(d)
ids = list(dict.fromkeys(x['artifact'] for x in records))
summary = []
for a in ids:
    # Every artifact manifest is audited locally; no computation rerun or credit.
    d = cli(['artifact', 'show', a], a + '.json')
    m = d['manifest']
    row = dict(artifact=a, name=m['output']['name'], role=d['output_role'], blob=d['output_blob'], bytes=m['output']['bytes'])
    h = d['output_blob']
    path = Q.parents[1] / 'blobs/sha256' / h[:2] / h
    assert hashlib.sha256(path.read_bytes()).hexdigest() == h
    summary.append(row)
save(O / 'inherited-artifact-inventory.json', summary)
print('ARTIFACTS', json.dumps(summary, indent=2))
# Preserve precise primary-source passages needed for study fit and reference leads.
passages = []
for rel, pat in [('outputs/upstream/PMC11014456-text.txt', r'P7|prolifer|Sox10|apop|macroph|Gerber|GSE|RNA.seq|Schwann cell number'), ('outputs/upstream/PMC5589416-text.txt', r'transcriptomes of P5|increas.*proliferating|RNA sequencing|sequence data|E-MTAB|PRJEB|GSE')]:
    for n, line in enumerate((P / rel).read_text().splitlines(), 1):
        if re.search(pat, line, re.I):
            passages.append(dict(source='questions/' + P.name + '/' + rel, line=n, text=line))
save(O / 'inherited-design-passages.json', passages)
# Condense actual source metadata with labels intact.
d = json.loads((P / 'inputs/metadata-GSE177037-specific.json').read_text())
meta = []
def fields(x):
    if isinstance(x, dict):
        if 'fields' in x and isinstance(x['fields'], dict):
            f = x['fields']
            meta.append({k:v for k,v in f.items() if any(z in k for z in ['title','characteristics','description','extract_protocol','data_processing','overall_design','summary','pubmed','relation'])})
        for v in x.values():
            fields(v)
    elif isinstance(x, list):
        for v in x:
            fields(v)
fields(d)
save(O / 'GSE177037-design-summary.json', meta)
print('GSE177037', json.dumps(meta, indent=2))
for text in ['development', 'purified', 'GSE137870', 'GSE177037']:
    d = cli(['data', 'search', '--text', text, '--limit', '15'], 'local-search-' + text + '.json')
    print('SEARCH', text, [(r['subject'], r['title']) for r in d['items']])
