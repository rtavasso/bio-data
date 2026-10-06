"""Inventory archive members and discovery metadata without opening outcome matrices."""
from pathlib import Path
import json,zipfile
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/upstream';O=Q/'outputs/upstream'
for p in I.glob('discovery-*.json'):
 d=json.loads(p.read_text())
 if 'resultList' not in d:continue
 print('\nQUERY',d.get('request',{}),'total',d.get('hitCount'))
 for r in d['resultList']['result']:print(r.get('id'),r.get('pmcid'),r.get('title'))
p=I/'FDFT1-supplements.zip'
with zipfile.ZipFile(p) as z:
 inv=[dict(name=x.filename,size=x.file_size,compressed=x.compress_size) for x in z.infolist()]
 (O/'FDFT1-archive-inventory.json').write_text(json.dumps(inv,indent=2));print('\nFDFT1 ARCHIVE',json.dumps(inv,indent=2))
 # Only preserve the linked native data archive and supplementary document; not scripts or images.
 for m in z.namelist():
  if m.lower().endswith(('.zip','.docx')):
   dst=I/Path(m).name
   with dst.open('xb') as f:f.write(z.read(m))
   print('EXTRACTED',dst.name)
   if dst.suffix=='.zip':
    with zipfile.ZipFile(dst) as zz:
     nested=[dict(name=x.filename,size=x.file_size,compressed=x.compress_size) for x in zz.infolist()]
     (O/'FDFT1-data-inventory.json').write_text(json.dumps(nested,indent=2));print('NESTED',json.dumps(nested,indent=2))
p=I/'PMC6185760-biocc.json';d=json.loads(p.read_text());lines=[]
for coll in d:
 for doc in coll['documents']:
  for pp in doc['passages']:lines.append(json.dumps(pp.get('infons',{}))+' '+pp.get('text',''))
(O/'PMC6185760-text.txt').write_text('\n'.join(lines)+'\n')
for s in lines:
 if any(k in s.lower() for k in ['rna-seq','pmp22','geo','accession','three mice','replicate']):print(s)
