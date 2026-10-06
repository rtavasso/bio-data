"""Inspect secondary validation coverage and provenance docs without claiming absence as zero."""
import csv
import gzip
import io
import json
from pathlib import Path
import re
import tarfile
from defusedxml import ElementTree as ET
import pyarrow.parquet as pq
Q=Path(__file__).resolve().parents[1]
for fn in ['QTD000538.permuted.tsv.gz']:
    with gzip.open(Q/'inputs/public'/fn,'rt') as f:
        rd=csv.DictReader(f,delimiter='\t');print('FIELDS',rd.fieldnames)
        rows=[dict(r,line=i+2,source=fn) for i,r in enumerate(rd) if any('ENSG00000109099' in v or '15260761' in v or '15265154' in v for v in r.values())]
    print('TWINS PERM',rows)
    (Q/'inputs/text/twins-perm-target.json').write_text(json.dumps(rows,indent=2))
with tarfile.open(Q/'inputs/public/v11-sqtl-susie.tar','r:') as t:
    result=[]
    for m in t:
        if not m.isfile() or not m.name.endswith('.parquet'):continue
        table=pq.read_table(io.BytesIO(t.extractfile(m).read()))
        if 'Adipose_Subcutaneous' in m.name:print('SQTL SUSIE schema',table.schema)
        for r in table.to_pylist():
            if any('ENSG00000109099' in str(v) for v in r.values()):result.append(dict(r,source=m.name))
    print('SQTL SUSIE TARGET',result)
    (Q/'inputs/text/gtex-sqtl-susie-target.json').write_text(json.dumps(result,indent=2))
for name in ['PMC3100536-bioc.xml','twins-primary-bioc.xml']:
    r=ET.fromstring((Q/'inputs/public'/name).read_bytes())
    rows=[f'[element={i}] '+ ' '.join(' '.join(e.itertext()).split()) for i,e in enumerate(r.iter()) if e.tag=='text']
    (Q/'inputs/text'/f'{name}.txt').write_text('\n'.join(rows)+'\n')
    for s in rows:
        if any(k in s.lower() for k in ['unrelated','relationship','relatedness','15106','15,106','linear mixed','female','covariat']):print(name,s[:2000])
for r in json.loads((Q/'inputs/public/catalogue-resource-tree.json').read_text())['tree']:
    if any(k in r['path'].lower() for k in ['metadata','paths','twins','compress','cc','gencord']):print('REPO',r['path'])
f=json.loads((Q/'inputs/public/gtex-openfiles.json').read_text())
def walk(x):
    if isinstance(x,dict):
        flat={k:v for k,v in x.items() if not isinstance(v,(dict,list))}
        if any('request' in str(v).lower() or 'all pairs' in str(v).lower() for v in flat.values()):print('REGISTRY',flat)
        for v in x.values():walk(v)
    elif isinstance(x,list):
        for v in x:walk(v)
walk(f)
