"""Read indexed discovery hits and freeze applicable inherited primary evidence."""
import hashlib
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

q = Path(__file__).resolve().parents[1]
s = q/'sources'
prior = q.parent/'q_e9e29d6eed344964'
d = json.loads((s/'independent-promoter-discovery-europepmc.json').read_text())

def inspect(resource):
    r = subprocess.run(['./bin/bio','data','show',resource],capture_output=True,text=True,check=True)
    data = json.loads(r.stdout)
    return resource,data

results = dict(ThreadPoolExecutor(max_workers=4).map(inspect,d['resources']))
(s/'independent-promoter-discovery-details.json').write_text(json.dumps(results,indent=2))
for resource, data in results.items():
    print(resource,json.dumps(data,ensure_ascii=False))
print('DISCOVERY_SCOPE',d['warnings'],'exhausted',d['exhausted'])

frozen = []
for name in ['PMC3100536-bioc.xml','PMC3100536-bioc.txt','PMC3100536-bioc.xml.receipt.json','PMC7430845-bioc.xml','PMC7430845-bioc.xml.receipt.json','rn5-Pmp22-promoter-sequence.json.receipt.json']:
    source = prior/'sources/primary'/name
    if not source.exists():
        print('NOT_PRESENT',name)
        continue
    dest = s/'inputs'/name
    shutil.copyfile(source,dest)
    frozen.append({'path':str(dest.relative_to(q)),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'bytes':dest.stat().st_size,'origin':'inherited exact bytes, not new retrieval'})
(s/'additional-primary-inputs.json').write_text(json.dumps(frozen,indent=2))
answer = json.loads((s/'community/design-critique-answer.json').read_text())
(s/'community/design-critique-answer.md').write_text(answer['content']['body'])
print('ANSWER',answer['content']['body'])
