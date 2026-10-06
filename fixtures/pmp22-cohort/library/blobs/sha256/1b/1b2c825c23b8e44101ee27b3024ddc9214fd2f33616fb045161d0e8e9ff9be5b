"""Compact audit of official metadata and primary-source identifiers."""
import csv
import json
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
p=Q/'inputs/public'
x=json.loads((p/'catalogue-paper-search.json').read_text())
print('Catalogue primary',[(r.get('pmcid'),r['title']) for r in x['resultList']['result']])
x=json.loads((Q/'outputs/inspection-v11.json').read_text())
print('Significant contexts',[(r['assay'],r['tissue'],r['qval']) for r in x['genes'] if float(r['qval'])<.05])
for r in x['covariates']:
    if any(t in r['member'] for t in ['Nerve_Tibial','Cells_Cultured_fibroblasts','Adipose_Subcutaneous']):print('covariates',r)
with (p/'catalogue-phenotype-paths.tsv').open() as f:
    for r in csv.DictReader(f,delimiter='\t'):
        if any(s in str(r) for s in ['TwinsUK','GENCORD']):print('PHENO PATH',r)
file=p/'QTD000100.complete.all.tsv.gz';print('Complete-path bytes (not completeness assertion)',file.stat().st_size)
