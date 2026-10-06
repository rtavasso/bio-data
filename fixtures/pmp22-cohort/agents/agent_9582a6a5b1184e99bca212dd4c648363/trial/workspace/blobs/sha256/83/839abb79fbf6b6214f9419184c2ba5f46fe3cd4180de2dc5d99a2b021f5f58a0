import json
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'sources/primary'
for f in ['pmp22-cis-nascent-search.json','schwann-cis-perturbation-search.json']:
 d=json.loads((P/f).read_text())
 for x in d['resultList']['result']:
  if x.get('id') in ['42801440','38456457','32356557','42507669']:
   print(json.dumps(x,indent=2))
for pmc in ['PMC3298281','PMC6077802','PMC7322568','PMC5181599']:
 d=json.loads((P/(pmc+'-meta.json')).read_text())
 for x in d['resultList']['result']:print(pmc,x.get('abstractText'))
