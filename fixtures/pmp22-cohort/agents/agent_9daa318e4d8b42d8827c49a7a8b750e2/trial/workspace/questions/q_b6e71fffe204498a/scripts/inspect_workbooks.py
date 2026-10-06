"""Inspect native workbook structure and input hashes before scientific arithmetic."""
from pathlib import Path
import hashlib
import importlib.util
import json
import gzip
import pandas as pd
from xls_values import read_xls

Q=Path(__file__).resolve().parents[1]
W=Q.parents[1]
P=Q.parent/'q_277f20df4b6b47cc'
O=Q/'outputs'

def blob(h):
    p=W/'blobs/sha256'/h[:2]/h
    assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    return p

print('PACKAGES', {m:bool(importlib.util.find_spec(m)) for m in ['xlrd','python_calamine','numpy','scipy','pandas','openpyxl','h5py','matplotlib']})
for n in ['elife-58591-supp1.xls','elife-58591-supp2.xls']:
    r=json.loads((Q/'inputs/managed'/(n+'.fetch.json')).read_text())
    p=blob(r['blob'])
    x=read_xls(p)
    print('WORKBOOK',n,list(x))
    for sn, sheet in x.items():
        print('STRUCTURE',sn,len(sheet['rows']),len(sheet['rows'][0]),'FORMULAS',len(sheet['formulas']),'ERRORS',len(sheet['errors']))
        d=pd.DataFrame(sheet['rows'][:4])
        print('SHEET',sn,d.to_string(index=False,header=False))
# Exact matrix header only, no target numerical extraction.
r=json.loads((P/'inputs/specific/fetch-discovery.json').read_text())
with gzip.open(blob(r['blob']),'rt') as f:
    print('REPAIR HEADER',next(f))
print('FIGLIA',pd.ExcelFile(blob('3c1be01fc49ea6b7eb7b527352c032e8e9987e4db78ed2a0bcc79b53b902b5b6'),engine='openpyxl').sheet_names)
