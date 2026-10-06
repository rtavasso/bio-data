"""Create compact source discovery views, preserving original JSON responses separately."""
import json
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'inputs/public'
queries=['validation-general-screen','candidate-secretion','candidate-acsl5-er']
for q in queries:
    d=json.loads((P/(q+'.json')).read_text())
    rows=d.get('resultList',{}).get('result',[])
    for r in rows:
        title=r.get('title','')
        if q=='candidate-acsl5-er' or '22660414'==r.get('id'):
            print(json.dumps({k:r.get(k) for k in ['id','pmcid','title','doi','abstractText','fullTextUrlList']},indent=2))
d=json.loads((P/'ncb2510-crossref.json').read_text())['message']
print('CROSSREF', json.dumps({k:d.get(k) for k in ['link','resource','relation','license']},indent=2))
