from pathlib import Path
import json
Q=Path(__file__).resolve().parents[1]; I=Q/'inputs/upstream'
for name in ['discovery-mtor-focused.json','discovery-lxr-focused.json']:
 d=json.loads((I/name).read_text());print(name,'hitCount',d['hitCount'])
 for r in d['resultList']['result']:
  t=r['title']
  if any(x in t.lower() for x in ['myelin','schwann cell','mammalian target','mtorc','peripheral nerve','progesterone','sterol','liver x']):
   print(r.get('pmcid'),r['id'],t)
   if any(x in t.lower() for x in ['dual function','cyclin','liver x','raptor','mtorc','mammalian target']):print(r.get('abstractText',''))
