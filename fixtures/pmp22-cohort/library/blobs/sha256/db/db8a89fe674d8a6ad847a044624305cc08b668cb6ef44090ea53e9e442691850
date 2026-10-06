"""Diagnose source-typed HCT116 identifiers after strict validation failed."""
from collections import Counter
from pathlib import Path
import io
import zipfile
import openpyxl
q=Path(__file__).resolve().parents[1]
z=zipfile.ZipFile(q/'inputs/http/pum-cnot-supp-r001.payload')
w=openpyxl.load_workbook(io.BytesIO(z.read('supp_078436.120_Supplemental_Table_S2.xlsx')), read_only=True, data_only=False)
for s in w:
    if s.title=='Legend':
        continue
    s.reset_dimensions()
    rows=[r for r in s.iter_rows(values_only=True) if any(v is not None for v in r)]
    rows=[r for r in rows[2:] if len(r)>6 and r[1] is not None]
    print(s.title, 'ROWS',len(rows),'IDENTIFIER TYPES',Counter(type(r[1]).__name__ for r in rows),'NONSTRING',[(type(r[1]).__name__,repr(r[1]),r[:7]) for r in rows if not isinstance(r[1],str)][:30], 'DUPLICATES', [(k,n) for k,n in Counter(str(r[1]) for r in rows).items() if n>1][:30])
