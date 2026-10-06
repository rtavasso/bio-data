"""Save current forum search results and exact relevant posts; no scientific code reuse."""
import json
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'inputs/community'
OUT.mkdir(parents=True, exist_ok=True)
TERMS = ['PMP22', 'RER1', 'UGGT1', 'glycosylation', 'cargo', 'surface', 'ABCA1', 'cholesterol', 'proteostasis', 'ENCODE', 'translation', 'PXD023091']
for term in TERMS:
    result = json.loads(subprocess.run(['./bin/bio', 'community', 'search', '--text', term, '--limit', '100'], capture_output=True, text=True, check=True).stdout)
    (OUT / f'search-{term}.json').write_text(json.dumps(result, indent=2))
    print(term, 'total', result['total'], 'next', result['next_offset'])
    for item in result['items']:
        print(item['subject'], item['title'], 'superseded', item.get('superseded_by'))
POSTS = ['post_ede3429c8d7a4485b7681fbf94798066', 'post_2e572838fec445898d74153361a71edf', 'post_e464a87a23c24cea85127b31d3bee6aa', 'post_d796b8a816a54b3a80d5662043ac90c9', 'post_7ecc0aec99444ae58621efc0514ad8ef']
for post in POSTS:
    data = json.loads(subprocess.run(['./bin/bio', 'community', 'show', post], capture_output=True, text=True, check=True).stdout)
    (OUT / f'{post}.json').write_text(json.dumps(data, indent=2))
    print('SAVED', post, data['content']['title'])
