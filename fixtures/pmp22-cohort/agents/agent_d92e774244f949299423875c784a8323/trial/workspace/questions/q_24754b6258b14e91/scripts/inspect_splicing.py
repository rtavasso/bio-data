"""Inspect compact target annotation, alternative first-exon junctions, and dataset eligibility."""
import csv
import json
from pathlib import Path
import re
import pyarrow.parquet as pq
Q=Path(__file__).resolve().parents[1]
o=json.loads((Q/'outputs/inspection-v11.json').read_text())
for x in o['genes']:
    if x['assay']=='sqtl' and x['tissue'] in ['Adipose_Subcutaneous','Ovary']:print('SQTL',x)
for t in ['Adipose_Subcutaneous','Ovary']:
    p=Q/'inputs/native/v11-sqtl'/f'{t}.v11.sQTLs.signif_pairs.parquet'
    rows=[]
    for b in pq.ParquetFile(p).iter_batches():
        d=b.to_pydict()
        for i,g in enumerate(d['group_id']):
            if g=='ENSG00000109099.16':rows.append({k:v[i] for k,v in d.items()})
    print(t,'significant_pair_count',len(rows))
    for ph in sorted({x['phenotype_id'] for x in rows}):
        xs=[x for x in rows if x['phenotype_id']==ph]
        print(ph,len(xs),'LEAD',min(xs,key=lambda x:x['pval_nominal']))
    (Q/'inputs/text'/f'{t}-sqtl-target.json').write_text(json.dumps(rows,indent=2))
g=json.loads((Q/'inputs/text/pmp22-gencode47.json').read_text())['rows']
for r in g:
    if r['type']=='exon' and r['attributes'].get('transcript_id') in ['ENST00000312280.9','ENST00000395938.7','ENST00000395936.7']:
        print('EXON',r['start1'],r['end1'],r['attributes']['transcript_id'],r['attributes'].get('exon_number'))
with (Q/'inputs/public/catalogue-metadata-r7.tsv').open() as f:
    for r in csv.DictReader(f,delimiter='\t'):
        if 'TwinsUK' in str(r):print('TWINS',r)
for name in ['novelty-focused.json','novelty-pmp22-qtl.json']:
    j=json.loads((Q/'inputs/public'/name).read_text());print(name,'total',j['hitCount'])
    for r in j['resultList']['result']:
        if 'PMP22' in (r.get('title','')+' '+r.get('abstractText','')).upper():
            print('LIT',r['id'],r.get('pmcid'),r['title'],re.sub('<[^>]+>',' ',r.get('abstractText',''))[:2500])
