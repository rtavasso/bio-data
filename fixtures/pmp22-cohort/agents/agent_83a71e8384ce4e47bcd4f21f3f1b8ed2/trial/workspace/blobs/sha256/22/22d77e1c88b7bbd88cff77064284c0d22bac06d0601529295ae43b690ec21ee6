"""Save and compact already-executed forum searches for the variant handoff."""
import json
from pathlib import Path
import shutil

q = Path(__file__).resolve().parents[1]
out = q / 'outputs' / 'variants-coordination'
out.mkdir(exist_ok=True)
log = Path('.hermes/cache/terminal-output/out-1791242498-34773-95b0.log')
shutil.copyfile(log, out / 'forum-search-readbacks.log')
results = []
for line in log.read_text().splitlines():
    if not line.startswith('{'):
        continue
    record = json.loads(line)
    if 'query' not in record:
        continue
    result = {'query': record['query'], 'total': record['total'],
              'next_offset': record.get('next_offset'), 'items': []}
    for item in record['items']:
        result['items'].append({key: item[key] for key in ('subject', 'title', 'superseded_by')})
        if record['query'] == 'sQTL':
            result['items'][-1]['summary'] = item['summary']
    results.append(result)
(out / 'search-review.json').write_text(json.dumps(results, indent=2, allow_nan=False))
print(json.dumps([r for r in results if r['query'] != 'PMP22'], indent=2))
