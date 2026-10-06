"""Inspect native GTEx tables, preserving target rows and source locators."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import pyarrow.parquet as pq
Q=Path(__file__).resolve().parents[1]
P=Q/'inputs/public'
result={'genes':[],'significant_pairs':[],'susie':[],'covariates':[],'groups':[],'archive_inventory':{}}
for kind in ['eqtl','sqtl']:
    for path in sorted((Q/'inputs/native'/f'v11-{kind}').glob('*Genes.txt.gz')):
        with gzip.open(path,'rt') as f:
            reader=csv.DictReader(f,delimiter='\t')
            rows=list(reader)
        targets=[dict(row,source=str(path.relative_to(Q)),source_line=i+2,assay=kind,
                 tissue=path.name.split('.v11')[0],table_rows=len(rows))
                 for i,row in enumerate(rows) if row.get('gene_name')=='PMP22' or
                 any('ENSG00000109099' in str(v) for k,v in row.items() if k in ['gene_id','phenotype_id'])]
        result['genes'].extend(targets)
        if not targets: print('ABSENT TESTED TABLE',kind,path.name)
    for path in sorted((Q/'inputs/native'/f'v11-{kind}').glob('*.parquet')):
        meta=pq.ParquetFile(path)
        print('PARQUET',path.name,meta.metadata.num_rows,meta.schema.names)
        gene='gene_id' if 'gene_id' in meta.schema.names else 'phenotype_id'
        for b in meta.iter_batches():
            d=b.to_pydict()
            for i,v in enumerate(d[gene]):
                if 'ENSG00000109099' in v:
                    result['significant_pairs'].append(dict({k:val[i] for k,val in d.items()},
                        source=str(path.relative_to(Q)),assay=kind,tissue=path.name.split('.v11')[0]))
for fn,label in [('v11-eqtl-susie.tar','susie'),('v11-eqtl-covariates.tar','covariates'),
                 ('v11-sqtl-groups.tar','groups')]:
    with tarfile.open(P/fn,'r:') as tar:
        result['archive_inventory'][fn]=[{'name':m.name,'bytes':m.size} for m in tar.getmembers()]
        for m in tar.getmembers():
            if not m.isfile(): continue
            if label=='susie' and m.name.endswith('.parquet'):
                data=tar.extractfile(m).read()
                table=pq.read_table(io.BytesIO(data))
                names=table.column_names
                key='gene_id' if 'gene_id' in names else 'phenotype_id'
                selected=[dict(r,member=m.name,source=fn) for r in table.to_pylist()
                          if 'ENSG00000109099' in str(r.get(key,''))]
                result[label].extend(selected)
            elif label in ['covariates','groups']:
                data=tar.extractfile(m).read()
                if m.name.endswith('.gz'): data=gzip.decompress(data)
                lines=data.decode().splitlines()
                if label=='covariates':
                    result[label].append({'member':m.name,'source':fn,'samples':len(lines[0].split('\t'))-1,
                                          'covariates':[x.split('\t')[0] for x in lines[1:]]})
                elif any('ENSG00000109099' in x for x in lines):
                    result[label].append({'member':m.name,'source':fn,'rows':len(lines),
                        'target_rows':[{'line':i+1,'value':x} for i,x in enumerate(lines) if 'ENSG00000109099' in x]})
for k in ['genes','susie','groups']:
    print(k,len(result[k]))
    if k!='groups':
        for x in result[k]:
            if k=='susie' or x.get('tissue') in ['Nerve_Tibial','Cells_Cultured_fibroblasts','Skin_Sun_Exposed_Lower_leg','Skin_Not_Sun_Exposed_Suprapubic']:
                print(json.dumps(x))
print('Significant pairs',len(result['significant_pairs']))
with (Q/'outputs/inspection-v11.json').open('x') as f:
    json.dump(result,f,indent=2,allow_nan=False)
    f.write('\n')
print('sha256',hashlib.sha256((Q/'outputs/inspection-v11.json').read_bytes()).hexdigest())
