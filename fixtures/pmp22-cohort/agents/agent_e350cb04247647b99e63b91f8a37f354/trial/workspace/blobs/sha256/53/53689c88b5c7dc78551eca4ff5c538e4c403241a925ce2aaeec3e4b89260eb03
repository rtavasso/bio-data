import json
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'sources'
for name in ['shared_artifact_search','shared_work_search']:
 d=json.loads((p/(name+'.json')).read_text())
 print(name,'total',d['total'],'next',d.get('next_offset'))
 for x in d['items']: print(x['subject'],x['title'])
d=json.loads((p/'corrected_package.json').read_text())
print('INPUT OBJECTS',json.dumps(d['input_objects'],indent=2))
print('report',json.dumps(d['report'],indent=2))
