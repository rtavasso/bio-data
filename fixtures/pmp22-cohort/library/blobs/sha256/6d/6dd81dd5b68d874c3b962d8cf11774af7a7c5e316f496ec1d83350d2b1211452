import json, os, zipfile
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_90f4fed27b7e4793'
w=Path(os.environ['BIO_WORKSPACE'])
d=json.loads((q/'outputs/artifact_0f7ede8968ed0aba576c856ccef0022cb3cdae962cfc1bc2d2f92bd0172b83f9-manifest.json').read_text())
for item in d['manifest']['derivation']['inputs']:
 h=item['blob'];p=w/'blobs/sha256'/h[:2]/h
 with p.open('rb') as f:b=f.read(150)
 print(h,p.stat().st_size,repr(b[:80]))
 if b.startswith(b'PK'):
  with zipfile.ZipFile(p) as z:print('ZIP',[(i.filename,i.file_size) for i in z.infolist()])
 elif p.stat().st_size<20000000 and b'\x00' not in b:
  try:
   txt=p.read_text()
   hits=[l for l in txt.splitlines() if 'Osgin1' in l and len(l)<2500]
   if hits: print('OSGIN', '\n'.join(hits[:5]))
  except UnicodeError:pass
