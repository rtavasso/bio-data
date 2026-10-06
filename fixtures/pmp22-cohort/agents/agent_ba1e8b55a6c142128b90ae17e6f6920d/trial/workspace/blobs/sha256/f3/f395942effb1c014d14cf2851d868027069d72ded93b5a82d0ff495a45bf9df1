import json
import sys
from pathlib import Path
q = Path(__file__).resolve().parents[1]
d = json.loads((q/'inputs'/sys.argv[1]).read_text())
print('hitCount', d['hitCount'], 'returned', len(d['resultList']['result']))
for r in d['resultList']['result']:
    title = r.get('title', '')
    if 'Review' not in r.get('pubTypeList', {}).get('pubType', []):
        print('\nID', r['id'], r.get('pmcid'), title)
        print('ABSTRACT:', r.get('abstractText', 'not available'))
        print('DOI', r.get('doi'))
