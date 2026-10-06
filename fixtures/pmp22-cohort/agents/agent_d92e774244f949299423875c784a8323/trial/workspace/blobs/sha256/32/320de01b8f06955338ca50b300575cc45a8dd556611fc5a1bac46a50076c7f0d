"""Safe source extraction and compact metadata checks; no downloaded code execution."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import zipfile
from defusedxml import ElementTree as ET
Q=Path(__file__).resolve().parents[1]
root=Q.parents[2]
art=json.loads((Q/'inputs/community/cis-source-artifact.json').read_text())
source=Path(art['path'])
assert hashlib.sha256(source.read_bytes()).hexdigest()==art['output_blob']
out=Q/'inputs/reused-cis';out.mkdir(exist_ok=True)
with zipfile.ZipFile(source) as z:
    names=z.namelist();print('CIS MEMBERS',names)
    for n in names:
        if n.endswith(('.xml','.txt','.json','.tsv','.html')) and not n.startswith('scripts/'):
            data=z.read(n)
            if any(x in n for x in ['3100536','3298281','5181599','manifest']):
                p=out/Path(n).name
                if not p.exists():p.write_bytes(data)
for p in (Q/'inputs/public').glob('*.xml'):
    try:
        tree=ET.fromstring(p.read_bytes())
        title=tree.find('.//article-title')
        print('ARTICLE',p.name,'' if title is None else ''.join(title.itertext()))
        text=[]
        for i,e in enumerate(tree.iter()):
            if e.tag in ['article-title','title','p','table','caption','text']:
                s=' '.join(' '.join(e.itertext()).split())
                if s:text.append(f'[{e.tag} element={i} id={e.get("id","")}] {s}')
        (Q/'inputs/text'/f'{p.name}.txt').write_text('\n\n'.join(text))
    except Exception as e: print('NOT PARSED',p.name,type(e).__name__)
gtf=Q/'inputs/public/gencode47.gtf.gz'
rows=[];headers=[]
with gzip.open(gtf,'rt') as f:
    for i,line in enumerate(f):
        if line.startswith('#'): headers.append(line.rstrip());continue
        if 'gene_id "ENSG00000109099.' not in line:continue
        cols=line.rstrip('\n').split('\t')
        a=dict(re.findall(r'(\w+) "([^"]*)"',cols[8]))
        rows.append({'line':i+1,'chromosome':cols[0],'type':cols[2],'start1':int(cols[3]),'end1':int(cols[4]),
                     'strand':cols[6],'attributes':a,'raw':line.rstrip('\n')})
print('GTF',headers,len(rows))
for r in rows:
    if r['type'] in ['gene','transcript']: print(r)
(Q/'inputs/text/pmp22-gencode47.json').write_text(json.dumps({'header':headers,'rows':rows},indent=2))
for p in ['QTD000100.permuted.tsv.gz','QTD000100.credible_sets.tsv.gz']:
    with gzip.open(Q/'inputs/public'/p,'rt') as f:
        reader=csv.DictReader(f,delimiter='\t');print(p,'columns',reader.fieldnames)
        target=[dict(r,source=p,line=i+2) for i,r in enumerate(reader)
                if any('ENSG00000109099' in str(v) for v in r.values())]
    print('PMP22',target)
    (Q/'inputs/text'/f'{p}.json').write_text(json.dumps(target,indent=2))
# GENCORD primary outcome is not in permutation/CS inspection unless it is the source lead;
# prediction was sealed before any GENCORD result inspection.
