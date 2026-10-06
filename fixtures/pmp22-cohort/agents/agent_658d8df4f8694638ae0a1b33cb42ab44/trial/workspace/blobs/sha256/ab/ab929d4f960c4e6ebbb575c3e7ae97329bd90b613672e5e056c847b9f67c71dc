"""Endpoint-focused audit of native tables, controls and provenance without inference."""
import collections
import json
from pathlib import Path
import openpyxl
ROOT = Path(__file__).resolve().parents[1]
P = ROOT/'inputs/public'

def read(name, sheet):
    wb = openpyxl.load_workbook(P/name, read_only=True, data_only=False, keep_links=False)
    rows = list(wb[sheet].iter_rows(values_only=True))
    wb.close()
    return rows
r = read('CAM40408-S4.xlsx','Sheet1')
print('HRP headers',r[0])
print('HRP plates',collections.Counter((row[0],row[5]) for row in r[1:]))
print('HRP controls',collections.Counter(row[2] for row in r[1:] if 'ontrol' in str(row[2])))
genes = sorted(set(row[2] for row in r[1:] if 'ontrol' not in str(row[2])))
print('HRP distinct genes',len(genes),genes)
for gene in ['GPR161','TMEM220','FAM98B','LMAN1','RER1','UGGT1','UGGT2','CANX','CALR','SEL1L','SYVN1','ABCA1','PMP22']:
    print('HRP targeted',gene,[row for row in r[1:] if row[2]==gene])
s6=read('CAM40408-S6.xlsx','1807_plateA_data_65')
print('Golgi genes', collections.Counter(row[1] for row in s6[1:]))
for name,sheet in [('JCI201297-data-native.xlsx','Sup. Fig. 4B'),('JCI201297-data-native.xlsx','Sup. Fig. 3A'),('JCI201297-data-native.xlsx','Sup. Fig. 3B'),('JCI201297-data-native.xlsx','Sup. Fig. 3C'),('JCI201297-data-native.xlsx','Fig. 3A'),('elife-63997-fig5-data1.xlsx','Sheet1'),('elife-63997-supp3.xlsx','Sheet1')]:
    print('\nSELECTED',name,sheet)
    for n,row in enumerate(read(name,sheet),1):
        vals={openpyxl.utils.get_column_letter(c):v for c,v in enumerate(row,1) if v is not None}
        if vals:
            print(n,json.dumps(vals, default=str))
print('PMP22 coverage in acquired UGGT files, exact words/accession Q01453:')
for path in sorted(P.glob('elife*.xlsx')):
    wb=openpyxl.load_workbook(path, read_only=True,data_only=False,keep_links=False)
    hits=[]
    for ws in wb:
        for row in ws:
            for c in row:
                if isinstance(c.value,str) and any(t in c.value.upper() for t in ['PMP22','Q01453','PERIPHERAL MYELIN PROTEIN 22']):
                    hits.append({'sheet':ws.title,'cell':c.coordinate,'value':c.value})
    wb.close()
    print(path.name,json.dumps(hits))
