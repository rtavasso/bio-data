"""Make a readable eligibility list from primary metadata returned by real discovery."""
import json
import subprocess
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

q = Path(__file__).resolve().parents[1]
s = q/'sources'
focused = json.loads((s/'independent-promoter-focused-discovery.json').read_text())

def get(resource):
    result = subprocess.run(['./bin/bio','data','show',resource],capture_output=True,text=True,check=True)
    return resource,json.loads(result.stdout)

extra = dict(ThreadPoolExecutor(max_workers=4).map(get,focused.get('resources',[])))
(s/'independent-promoter-focused-details.json').write_text(json.dumps(extra,indent=2))
all_hits = json.loads((s/'independent-promoter-discovery-details.json').read_text()) | extra
seen = set()
lines = []
for resource, data in all_hits.items():
    for profile in data.get('profiles',[]):
        record = profile.get('facts',{}).get('source_record',{})
        if 'title' not in record:
            continue
        key = (record.get('id'),record['title'])
        if key in seen:
            continue
        seen.add(key)
        title = record['title']
        abstract = record.get('abstractText','')
        lines.extend([f"RESOURCE {resource}; id={record.get('id')}; pmcid={record.get('pmcid')}; year={record.get('pubYear')}; focused={resource in extra}",title,textwrap.fill(abstract,140),''])
(s/'literature-candidates.txt').write_text('\n'.join(lines))
print('READABLE_METADATA_RECORDS',len(seen),'FOCUSED_RESOURCES',len(extra),'FOCUSED_EXHAUSTED',focused.get('exhausted'))
print('\n'.join(lines))
