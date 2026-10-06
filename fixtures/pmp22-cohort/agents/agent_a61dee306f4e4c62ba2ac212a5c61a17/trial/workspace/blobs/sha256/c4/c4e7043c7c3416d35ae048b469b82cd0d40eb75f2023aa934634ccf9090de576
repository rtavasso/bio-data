from pathlib import Path
import zipfile,json,hashlib,io
from openpyxl import load_workbook
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/upstream';O=Q/'outputs/upstream'
p=I/'Figlia2017-supplements.zip';print('ZIP',zipfile.is_zipfile(p))
if zipfile.is_zipfile(p):
 z=zipfile.ZipFile(p);items=[dict(name=x.filename,bytes=x.file_size) for x in z.infolist()];(O/'Figlia-inventory.json').write_text(json.dumps(items,indent=2));print(json.dumps(items,indent=2))
 targets=[x.filename for x in z.infolist() if 'fig3-data1' in x.filename and x.filename.endswith('.xlsx')];assert len(targets)==1,targets
 b=z.read(targets[0]);dest=I/Path(targets[0]).name;assert not dest.exists();dest.write_bytes(b)
 w=load_workbook(io.BytesIO(b),read_only=True,data_only=False)
 # Header-only inspection. No validation-gene outcome values printed.
 info=[]
 for s in w:
  headers=list(s.iter_rows(min_row=1,max_row=2,values_only=True)); info.append(dict(sheet=s.title,rows=s.max_row,cols=s.max_column,headers=headers))
 (O/'Figlia-structure.json').write_text(json.dumps(info,indent=2,default=str));print(json.dumps(info,indent=2,default=str))
 (O/'Figlia-extraction.json').write_text(json.dumps(dict(archive_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),member=targets[0],output=str(dest.relative_to(Q)),sha256=hashlib.sha256(b).hexdigest()),indent=2))
