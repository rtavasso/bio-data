"""Summarize official file registry and API enums without executing site code."""
import json
from pathlib import Path
Q = Path(__file__).resolve().parents[1]
a=json.loads((Q/'inputs/public/gtex-openapi.json').read_text())
for key in ['DatasetId','AvailableProjects','GencodeVersion']:
    print(key, a['components']['schemas'][key])
f=json.loads((Q/'inputs/public/gtex-files.json').read_text())
print('type',type(f).__name__)

def walk(x):
    if isinstance(x,dict):
        if any(isinstance(v,str) and any(s in v.lower() for s in ['eqtl','sqtl','readme','v11']) for v in x.values()):
            print(json.dumps({k:v for k,v in x.items() if not isinstance(v,(dict,list))}))
        for v in x.values():
            walk(v)
    elif isinstance(x,list):
        for v in x:
            walk(v)
walk(f)
for path, ops in a['paths'].items():
    if any(x in path for x in ['tissueSiteDetail','transcript','Transcript']):
        print(path,[(p['name'],p.get('schema')) for p in ops.get('get',{}).get('parameters',[])])
