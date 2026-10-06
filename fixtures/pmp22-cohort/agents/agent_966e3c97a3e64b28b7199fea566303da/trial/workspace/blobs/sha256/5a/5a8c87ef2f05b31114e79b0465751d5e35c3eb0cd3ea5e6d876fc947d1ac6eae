"""Inspect archive spreadsheets without formulas or arbitrary extraction."""
import gzip
import hashlib
import io
import json
import zipfile
from pathlib import Path
import openpyxl

R=Path(__file__).resolve().parents[1]
S=R/'inputs'/'sources'
report=[]
with zipfile.ZipFile(S/'PMC4341466-supp.zip') as z:
    print('MEMBERS',z.namelist())
    for member in z.namelist():
        if not member.endswith('.xlsx'):
            continue
        data=z.read(member)
        dest=S/Path(member).name
        if not dest.exists():
            dest.write_bytes(data)
        assert hashlib.sha256(dest.read_bytes()).hexdigest()==hashlib.sha256(data).hexdigest()
        wb=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=False)
        sheets=[]
        for ws in wb:
            first=[]
            for i,row in enumerate(ws.iter_rows(values_only=True)):
                if i==5:
                    break
                first.append(row)
            sheets.append({'sheet':ws.title,'rows':ws.max_row,'cols':ws.max_column,'first_rows':first})
        report.append({'member':member,'sha256':hashlib.sha256(data).hexdigest(),'sheets':sheets})
print(json.dumps(report,indent=2,default=str))
with gzip.open(S/'hg19-kgXref.txt.gz','rt') as f:
    first=[next(f) for _ in range(3)]
print('kgXref header',first)
(R/'outputs'/'secondary-supplement-inspection.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
