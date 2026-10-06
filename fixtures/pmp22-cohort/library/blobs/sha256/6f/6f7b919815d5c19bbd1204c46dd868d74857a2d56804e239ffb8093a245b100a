"""Inspect source author DE mapping and supplement eligibility, without gene selection."""
import gzip
import json
from pathlib import Path
import zipfile
import pandas as pd

Q = Path(__file__).resolve().parents[1]
receipt = json.loads((Q / 'outputs/Acly-deg-fetch.json').read_text())
h = receipt['blob']
p = Q.parents[1] / 'blobs/sha256' / h[:2] / h
with gzip.open(p, 'rt') as f:
    for _ in range(3):
        print(f.readline()[:3000])
for label in ['Acly', 'CMT']:
    meta = json.loads((Q / 'outputs' / f'{label}-acquired.json').read_text())
    df = pd.read_csv(meta['path'], compression='gzip', sep=',' if label == 'Acly' else '\t')
    if label == 'Acly':
        symbols = df.gene_name
    else:
        symbols = df.gene_id.str.split('_', n=1).str[1]
    panel = json.loads((Q / 'inputs/analysis-plan.json').read_text())['modules']
    all_requested = sorted(set(sum(panel.values(), [])))
    print(label, 'shape', df.shape, 'panel coverage', [(s, int((symbols == s).sum())) for s in all_requested])
    print(label, 'duplicate symbol examples', symbols[symbols.duplicated(keep=False)].head(12).tolist())
print('ACLY SUPPLEMENT PAYLOAD', (Q / 'inputs/Acly-supplements.zip').read_text())
print('SCAP BIOC prefix', (Q / 'inputs/PMC2795508-bioc.json').read_text()[:300])
with zipfile.ZipFile(Q / 'inputs/Fledrich2018-supplements.zip') as z:
    name = '41467_2018_5420_MOESM6_ESM.xls'
    p = Q / 'inputs' / name
    if not p.exists():
        p.write_bytes(z.read(name))
print('Supplement XLS magic', p.read_bytes()[:30])
