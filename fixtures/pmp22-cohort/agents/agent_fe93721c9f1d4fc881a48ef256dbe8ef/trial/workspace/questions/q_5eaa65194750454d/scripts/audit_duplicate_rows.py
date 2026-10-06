"""Audit native workbook duplicate identifiers; never silently discard rows."""
import json
from pathlib import Path
import openpyxl
import pandas as pd
q=Path(__file__).resolve().parents[1]
h='13a3d8dd3037b8f3d81219c6c7e84d121d5fe915cd88a4ca1d411eaa0257fe8d'
p=q.parents[1]/'blobs/sha256'/h[:2]/h
with p.open('rb') as f:
    wb=openpyxl.load_workbook(f,read_only=True,data_only=False)
    rows=wb[wb.sheetnames[0]].iter_rows(values_only=True)
    d=pd.DataFrame(rows,columns=next(rows))
# DataFrame constructor may evaluate data before columns expression? Explicit output checks below.
print('HEADERS',list(d.columns))
if 'Identifier' not in d:
    raise ValueError('native header not preserved')
d.insert(0,'source_row',range(2,len(d)+2))
x=d[d['Identifier'].duplicated(keep=False) | d['Identifier'].isna()]
print('NROWS',len(d),'DUP_OR_NULL',len(x))
print(x.to_string(index=False))
x.to_csv(q/'outputs/nedd4-duplicate-identifiers.tsv',sep='\t',index=False)
(q/'outputs/nedd4-duplicate-audit.json').write_text(json.dumps({'native_rows':len(d),'duplicates_or_null':len(x),'all_duplicate_rows_empty_except_source_row':bool(x.drop(columns='source_row').isna().all().all()),'source_blob':h},indent=2)+'\n')
