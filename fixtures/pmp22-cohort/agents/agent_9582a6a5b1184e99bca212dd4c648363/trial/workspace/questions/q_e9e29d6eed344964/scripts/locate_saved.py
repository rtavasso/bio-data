import json, os, hashlib
from pathlib import Path
p=Path(__file__).resolve().parents[1]
lib=Path(os.environ['BIO_COMMUNITY'])/'library/blobs/sha256'
a=json.loads((p/'sources/consolidation-artifact.json').read_text())
h=a['output_blob']
src=lib/h[:2]/h
data=json.loads(src.read_text())
(p/'sources/consolidation-audit.json').write_text(json.dumps(data,indent=2)+'\n')
print('audit',h, 'keys',list(data))
terms=['3100536','3298281','7322568','139321','tss-regulatory','tss','continuation']
def walk(obj,loc=''):
 if isinstance(obj,dict):
  text=json.dumps(obj)
  if any(t.lower() in text.lower() for t in terms):
   if len(text)<4000: print(loc,json.dumps(obj,indent=2))
   else:
    for k,v in obj.items():walk(v,loc+'/'+k)
 elif isinstance(obj,list):
  for i,v in enumerate(obj):walk(v,loc+'/'+str(i))
walk(data)
for x in a['manifest']['derivation']['inputs']:
 h=x['blob']; src=lib/h[:2]/h
 if src.stat().st_size<10_000_000:
  b=src.read_bytes()
  if any(t.encode() in b for t in terms[:5]):
   print('MATCH INPUT',h,len(b),b[:150])
   try:
    d=json.loads(b); (p/'sources'/('prior-'+h+'.json')).write_text(json.dumps(d,indent=2)+'\n'); walk(d,h)
   except (ValueError,UnicodeDecodeError):pass
