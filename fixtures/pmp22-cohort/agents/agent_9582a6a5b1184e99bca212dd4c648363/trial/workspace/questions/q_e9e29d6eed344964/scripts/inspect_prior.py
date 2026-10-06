import json
from pathlib import Path
import os
root=Path(__file__).resolve().parents[1]
lib=Path(os.environ['BIO_COMMUNITY'])/'library/blobs/sha256'
items={'notebook_manifest':'e054cae33492c105e41221766e86dc067d7c5dfeaf75fc8409c23b468964166b','mechanism_map':'043b8a66d39ab07ff0ad7ad179e3d13e36e6c88f5b480d4f3d25f6e43ebe287e','corrected_package':'ec40eba9a7bdd48c792a6163e7a40a9e4105cdc5aadc492977bbaf42f9eea2a3'}
for name,h in items.items():
    data=json.loads((lib/h[:2]/h).read_text())
    out=root/'sources'/f'{name}.json'
    out.write_text(json.dumps(data,indent=2)+'\n')
    print(name,list(data) if isinstance(data,dict) else type(data).__name__)
    if name=='notebook_manifest': print(json.dumps(data,indent=2))

def walk(obj, loc=''):
    if isinstance(obj,dict):
        text=json.dumps(obj)
        if any(s.lower() in text.lower() for s in ['139321','3100536','3298281','7322568','tss-regulatory']):
            if len(text)<6000:
                print(loc, json.dumps(obj,indent=2))
            else:
                for k,v in obj.items(): walk(v,loc+'/'+k)
    elif isinstance(obj,list):
        for i,v in enumerate(obj): walk(v,loc+'/'+str(i))
walk(json.loads((root/'sources/corrected_package.json').read_text()))
