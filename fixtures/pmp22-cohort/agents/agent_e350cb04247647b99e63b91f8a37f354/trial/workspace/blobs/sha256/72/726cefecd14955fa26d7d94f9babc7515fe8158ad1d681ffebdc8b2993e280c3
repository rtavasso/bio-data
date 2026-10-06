import hashlib, json, zipfile
from pathlib import Path
import openpyxl
P=Path(__file__).resolve().parents[1]
src=P/'sources/primary/PMC7430845-supplements.zip'
name='12864_2020_6963_MOESM2_ESM.xlsx'
with zipfile.ZipFile(src) as z:
 b=z.read(name)
p=P/'sources/primary'/name;p.write_bytes(b)
print('member sha256',hashlib.sha256(b).hexdigest())
w=openpyxl.load_workbook(p,read_only=True,data_only=False)
for s in w:
 print('SHEET',s.title,s.max_row,s.max_column)
 for row in list(s.iter_rows(min_row=1,max_row=5,values_only=True)):print(row)
 if s==w.worksheets[0]:
  for i,row in enumerate(s.iter_rows(values_only=True),1):
   if any(isinstance(x,str) and x.lower()=='pmp22' for x in row):print('PMP22 row',i,row)
