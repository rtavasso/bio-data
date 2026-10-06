"""Find source locators within explicit shared manifest; no library writes."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'inputs' / 'prior'
LIB = os.environ['BIO_COMMUNITY'] + '/library'

def cli(*args):
    return json.loads(subprocess.run(['./bin/bio', *args], check=True, capture_output=True, text=True).stdout)

post = cli('community', 'show', 'post_9d25fbe9084740baba1e8b48870d434e')
(OUT/'seed-post.json').write_text(json.dumps(post, indent=2))
for aid in post['content']['evidence']['artifacts']:
    meta = cli('--workspace', LIB, 'artifact', 'show', aid)
    print(aid, meta['manifest']['title'], meta['manifest']['output']['name'], meta['output_blob'])
for filename in ['mechanisms.r021.json', 'verification-r003.json', 'ec40eba9a7bdd48c792a6163e7a40a9e4105cdc5aadc492977bbaf42f9eea2a3.pretty.json']:
    path = OUT/filename if (OUT/filename).exists() else ROOT/'inputs/community'/filename
    data = json.loads(path.read_text())
    def walk(v, loc='', label=filename):
        if isinstance(v,dict):
            if any(re.search('8191293|4227013|co.?ip|LFQ', str(x), re.I) for x in v.values() if isinstance(x,str)):
                print(label, loc, json.dumps(v))
            for k,x in v.items():
                if isinstance(x,(dict,list)):
                    walk(x, loc+'/'+k)
        elif isinstance(v,list):
            for i,x in enumerate(v):
                walk(x, loc+'/'+str(i))
    walk(data)
meta=cli('--workspace', LIB, 'object', 'show', '23f94e75dab1ce2b57cda1ca09d1552867e8608357dd04e88572f0bcdbe907bf')
raw=Path(meta['path']).read_bytes()
assert hashlib.sha256(raw).hexdigest()==meta['blob']
doc=json.loads(raw)
(OUT/'seed-evidence-manifest.json').write_text(json.dumps(doc,indent=2))
print('EVIDENCE MANIFEST KEYS',list(doc))
