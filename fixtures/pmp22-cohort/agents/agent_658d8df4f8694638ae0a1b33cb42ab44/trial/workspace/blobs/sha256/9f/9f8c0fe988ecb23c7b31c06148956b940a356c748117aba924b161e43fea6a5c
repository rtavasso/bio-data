from pathlib import Path
import json,zipfile,re
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/upstream';O=Q/'outputs/upstream'
with zipfile.ZipFile(I/'NEDD-supplements.zip') as z:
 inv=[dict(name=x.filename,bytes=x.file_size) for x in z.infolist()];(O/'NEDD-supplement-inventory.json').write_text(json.dumps(inv,indent=2));print(json.dumps(inv,indent=2))
 for n in z.namelist():
  if n.endswith('_sm.pdf'):(I/Path(n).name).write_bytes(z.read(n))
d=json.loads((I/'PMC5956991-biocc.json').read_text());lines=[]
for coll in d:
 for doc in coll['documents']:
  for pp in doc['passages']:lines.append(json.dumps(pp.get('infons',{}))+' '+pp.get('text',''))
(O/'PMC5956991-text.txt').write_text('\n'.join(lines)+'\n')
for s in lines:
 if re.search(r'GSE\d+|PRJEB\d+|accession|RNA-sequenc',s,re.I):print(s)
