"""Read the actual successful retry records; a previous HTTP 503 is not absence."""
import json
import subprocess
import textwrap
from pathlib import Path

q = Path(__file__).resolve().parents[1]
s = q/'sources'
result = json.loads((s/'independent-promoter-focused-retry.json').read_text())
assert not result['warnings']
records = {}
lines = []
for resource in result['resources']:
    data = json.loads(subprocess.run(['./bin/bio','data','show',resource],capture_output=True,text=True,check=True).stdout)
    records[resource] = data
    seen = set()
    for profile in data.get('profiles',[]):
        r = profile.get('facts',{}).get('source_record',{})
        if not r.get('title') or r['title'] in seen:
            continue
        seen.add(r['title'])
        lines.extend([f"{resource} PMID={r.get('id')} PMCID={r.get('pmcid')} YEAR={r.get('pubYear')}",r['title'],textwrap.fill(r.get('abstractText',''),140),''])
(s/'independent-promoter-retry-details.json').write_text(json.dumps(records,indent=2))
(s/'independent-promoter-retry-review.txt').write_text('\n'.join(lines))
print('\n'.join(lines))
