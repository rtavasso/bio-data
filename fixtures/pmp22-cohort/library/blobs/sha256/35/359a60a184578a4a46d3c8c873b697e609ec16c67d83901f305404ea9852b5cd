"""Inspect newly selected matrix structure and annotation-only native export fields."""
import gzip,json,os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';ws=q.parents[1]
x=json.loads((q/'outputs/fetch-GSE108231.json').read_text());print('FETCH',x)
if x.get('blob'):
    h=x['blob'];p=ws/'blobs/sha256'/h[:2]/h
    with gzip.open(p,'rt') as f:
        for i in range(3):print('MATRIX_ROW',next(f).strip())
f=json.loads((q/'outputs/fields-GSE108231.json').read_text());print('STUDY_PUBMED',f.get('GSE108231',{}).get('Series_pubmed_id'))
for acc,fields in f.items():
    if acc.startswith('GSM'):print('SAMPLE_MAP',acc,fields.get('Sample_title'),fields.get('Sample_description'),fields.get('Sample_relation'))
with (q/'inputs/public/Schwanncellscontrol1-annotation-only.txt').open() as f:
    for line in f:
        if line.startswith('FEATURES'):
            header=line.rstrip('\n').split('\t');print('NATIVE_FEATURE_FIELDS',header)
            row=next(f).rstrip('\n').split('\t');print('ANNOTATION_EXAMPLE',{k:v for k,v in zip(header,row) if k in ['ProbeName','GeneName','SystematicName','Description','ControlType']});break
