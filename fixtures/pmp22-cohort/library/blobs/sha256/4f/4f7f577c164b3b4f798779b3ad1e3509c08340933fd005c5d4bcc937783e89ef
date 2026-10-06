"""Compact first-outcome and current file metadata inspection."""
import json
from collections import Counter
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
for fn in ['gene-v39.json','v8-eqtl-pmp22.json','v8-sqtl-pmp22.json']:
    o=json.loads((Q/'inputs/public'/fn).read_text())
    print(fn, o.get('paging_info'),o.get('data',[])[:2])
    if fn.endswith('eqtl-pmp22.json'):
        rows=o['data']
        print(Counter(x['tissueSiteDetailId'] for x in rows))
        for t in sorted({x['tissueSiteDetailId'] for x in rows}):
            xs=[x for x in rows if x['tissueSiteDetailId']==t]
            print(t, min(xs,key=lambda x:x['pValue']))
o=json.loads((Q/'inputs/public/gtex-openfiles.json').read_text())
print('OPENFILES type',type(o).__name__)
def walk(x):
    if isinstance(x,dict):
        flat={k:v for k,v in x.items() if not isinstance(v,(dict,list))}
        text=str(flat)
        if ('v10' in text or 'v11' in text) and any(v in text.lower() for v in ['qtl','readme']):
            print(json.dumps(flat))
        for v in x.values(): walk(v)
    elif isinstance(x,list):
        for v in x: walk(v)
walk(o)
