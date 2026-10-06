"""Inspect measurement schemas, exact GENCODE19 target interval and unselected target rows."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
q=Path(__file__).resolve().parents[1]
p=q/'inputs/http/gencode19-encode-gtf-r001.payload'
assert hashlib.md5(p.read_bytes()).hexdigest()=='fdc985b094ef823e5a51164cd109f4e8'
genes={}
features=[]
with gzip.open(p,'rt') as f:
    for line in f:
        if line.startswith('#'):
            continue
        a=line.rstrip('\n').split('\t')
        attrs=dict(re.findall(r'(\w+) "([^"]*)"',a[8]))
        if a[2]=='gene':
            genes[attrs['gene_id']]={'name':attrs['gene_name'],'type':attrs['gene_type'],'chrom':a[0],'start':int(a[3])-1,'end':int(a[4]),'strand':a[6]}
        if attrs.get('gene_name')=='PMP22':
            features.append({'chrom':a[0],'feature':a[2],'start':int(a[3])-1,'end':int(a[4]),'strand':a[6],'attributes':attrs})
assert len([x for x in features if x['feature']=='gene'])==1
(q/'inputs/views/gencode19-genes.json').write_text(json.dumps(genes,indent=2))
(q/'inputs/views/pmp22-gencode19-features.json').write_text(json.dumps(features,indent=2))
target=next(x for x in genes if genes[x]['name']=='PMP22')
print('PMP22',target,genes[target], 'TRANSCRIPTS', [x['attributes']['transcript_id'] for x in features if x['feature']=='transcript'])
print('GENES',len(genes))
rows=json.loads((q/'inputs/selection-r001.json').read_text())
for cell in ['HepG2','K562']:
    for role in ['idr_peaks','de_paired','de_batch']:
        x=next(x for x in rows if x['cell']==cell and x['role']==role)
        path=q/'inputs/http'/('file-'+x['file']['File accession']+'-r001.payload')
        if role=='idr_peaks':
            with gzip.open(path,'rt') as f:
                print('PEAK SCHEMA',x['rbp'],cell,[next(f).rstrip() for _ in range(3)])
        else:
            with path.open() as f:
                data=list(csv.reader(f,delimiter='\t'))
            print('DE SCHEMA',cell,role,len(data),'HEADER',data[0],'FIRST',data[1])
            print('TARGET ROW',[a for a in data[1:] if a[0].split('.')[0]==target.split('.')[0]])
