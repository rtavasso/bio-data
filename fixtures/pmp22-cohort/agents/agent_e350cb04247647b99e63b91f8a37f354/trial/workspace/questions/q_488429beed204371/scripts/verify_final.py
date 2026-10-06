"""Final read-only catalog/forum verification plus saved audit, without reanalysis."""
import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q/'outputs'
index = json.loads((out/'publication-index.json').read_text())

def bio(*args):
    return json.loads(subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True).stdout)

main = bio('community','show',index['main'])
peer = bio('community','show',index['selectivity_handoff'])
assert set(main['content']['evidence']['artifacts'])==set(index['products'].values())|{index['bundle']}
assert len(main['content']['evidence']['artifacts'])==21
for name,aid in index['products'].items():
    info = bio('artifact','show',aid)
    assert info['output_blob']==hashlib.sha256((out/name).read_bytes()).hexdigest()
assert index['bundle'] in peer['content']['evidence']['artifacts']
for name in ['addendum-final-readback.json','selectivity-final-readback.json','inbox-final.json','inbox-sent-final.json']:
    obj = json.loads((q/'sources/community'/name).read_text())
    if isinstance(obj,dict):
        print(name,'superseded_by',obj.get('superseded_by'),'replies',obj.get('replies'))
    else:
        print(name,json.dumps(obj))
validation = json.loads((out/'validation.json').read_text())
assert validation['checks_passed']==129
result = {'main_post':index['main'],'peer_handoff':index['selectivity_handoff'],
          'verified_quantitative_artifacts':len(index['products']),'published_artifact_refs':len(main['content']['evidence']['artifacts']),
          'validation_checks':validation['checks_passed'],'main_superseded_by':main['superseded_by'],
          'bundle':index['bundle'],'status':'verified'}
(out/'final-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
