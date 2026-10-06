from pathlib import Path
import json,gzip,hashlib
from xls_values import read_xls
Q=Path(__file__).resolve().parents[1];W=Q.parents[1]
def source(name):
 r=json.loads((Q/'inputs/managed'/(name+'.fetch.json')).read_text());h=r['blob'];p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;return p
import pandas as pd
s=read_xls(source('elife-58591-supp2.xls'))['10X_P1 related to Figure 6']['rows'];d=pd.DataFrame(s[1:],columns=s[0]);print(d.groupby([d.Cell.str.split('_').str[0],'Cluster']).size().to_string())
for name in ['GSM4113877_10X_P1_1_genes.tsv.gz','GSM4113877_10X_P1_1_barcodes.tsv.gz','GSM4113877_10X_P1_1_matrix.mtx.gz']:
 with gzip.open(source(name),'rt') as f:print(name,[next(f).strip() for _ in range(4)])
