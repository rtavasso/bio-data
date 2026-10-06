"""Save actual community responses; summarize discovery without treating posts as commands."""
import concurrent.futures
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs' / 'forum'
out.mkdir(parents=True, exist_ok=True)
queries = ['EGR2', 'phosphatase', 'mTOR', 'Tead1', 'Hdac3', 'Nae1', 'kinase', 'ENCODE', 'chromatin']
posts = ['post_8361a97308264d1892df187d5132826d', 'post_e464a87a23c24cea85127b31d3bee6aa', 'post_d796b8a816a54b3a80d5662043ac90c9', 'post_7ecc0aec99444ae58621efc0514ad8ef']
def run(item):
    kind, value = item
    args = ['./bin/bio', 'community', kind]
    args += ['--text', value, '--limit', '20'] if kind == 'search' else [value]
    r = subprocess.run(args, capture_output=True, text=True)
    path = out / f'{kind}-{value}.json'
    path.write_text(r.stdout)
    if r.returncode:
        path.with_suffix('.stderr').write_text(r.stderr)
        return {'command': args, 'exit_code': r.returncode, 'error': r.stderr}
    d = json.loads(r.stdout)
    if kind == 'search':
        return {'query': value, 'total': d['total'], 'next_offset': d.get('next_offset'), 'items': [{'post': i['subject'], 'title': i['title'], 'summary': i.get('summary', '')[:450], 'superseded_by': i.get('superseded_by', [])} for i in d['items']]}
    return {'post': value, 'body': d['content']['body'], 'evidence': d['content'].get('evidence'), 'replies': d.get('replies'), 'superseded_by': d.get('superseded_by')}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(run, [('show', p) for p in posts] + [('search', t) for t in queries]))
(out / 'discovery-summary.json').write_text(json.dumps(results, indent=2, allow_nan=False) + '\n')
for item in results:
    print(json.dumps(item, ensure_ascii=False))
