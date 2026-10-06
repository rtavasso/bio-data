"""Inspect saved forum results and source metadata only; no scientific reanalysis."""
import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
posts = {}
for term in ('tead', 'stiffness'):
    result = json.loads((q / f'sources/community/{term}-followup-search.json').read_text())
    assert result.get('next_offset') is None
    print('SEARCH', term, 'RESULTS', len(result['items']))
    for item in result['items']:
        posts[item['subject']] = item
lines = []
for post, item in posts.items():
    print(post, item['title'], 'SUPERSEDED_BY', item.get('superseded_by'))
    lines.extend([post, item['title'], item.get('summary', ''), ''])
(q / 'sources/community/tead-followup-review.txt').write_text('\n'.join(lines))
metadata = json.loads((q / 'sources/primary/PMC5181599-meta.json').read_text())
article = metadata['resultList']['result'][0]
print('PRIMARY_ABSTRACT', article['pmcid'], article['title'])
print(article['abstractText'])
(q / 'sources/tead-followup-abstract.txt').write_text(article['abstractText'])
