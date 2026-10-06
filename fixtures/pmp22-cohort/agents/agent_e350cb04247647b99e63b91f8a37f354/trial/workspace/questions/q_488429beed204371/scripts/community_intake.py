"""Save actual current community results before choosing new analysis inputs."""
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'sources/community'
out.mkdir(parents=True, exist_ok=True)
queries = ['GSE139321', 'Tn5Prime', 'cAMP', 'SOX10', 'promoter ratio', 'P1 P2']
posts = ['post_3f7bd6e66753476fb33ec6d9da9cbcc8', 'post_162b76b9910c40e39e09f0f033fbadea', 'post_c344fef84f344beca27925ec3f9ce940', 'post_d6a2ae5d24b64dd9a5069f793e51e049']
jobs = [(f'search-{i}', ['community', 'search', '--text', text, '--limit', '100']) for i, text in enumerate(queries)]
jobs += [(post, ['community', 'show', post]) for post in posts]

def get(job):
    name, args = job
    r = subprocess.run(['./bin/bio', *args], capture_output=True, text=True)
    (out / f'{name}.json').write_text(r.stdout)
    if r.returncode:
        (out / f'{name}.stderr').write_text(r.stderr)
        raise RuntimeError((name, r.returncode, r.stdout, r.stderr))
    data = json.loads(r.stdout)
    if name.startswith('search-'):
        assert data.get('next_offset') is None, 'Search requires pagination'
    else:
        (out / f'{name}.md').write_text(data['content']['body'])
    return name, data

results = dict(ThreadPoolExecutor(max_workers=4).map(get, jobs))
seen = {}
for i, query in enumerate(queries):
    result = results[f'search-{i}']
    print('QUERY', query, 'COUNT', len(result['items']), 'TOTAL', result.get('total'))
    for item in result['items']:
        seen[item['subject']] = item
(out / 'query-map.json').write_text(json.dumps(queries, indent=2))
lines = []
for post, item in seen.items():
    print(post, item['title'])
    lines.extend([post, item['title'], 'superseded_by=' + str(item.get('superseded_by')), item.get('summary', ''), ''])
(out / 'search-review.txt').write_text('\n'.join(lines))
for post in posts:
    print('READ_POST', post, 'REPLIES', results[post].get('replies'), 'SUPERSEDED_BY', results[post].get('superseded_by'))
