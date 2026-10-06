"""Save current community evidence and produce compact search summaries."""
import json
import pathlib
import subprocess

Q = pathlib.Path(__file__).resolve().parents[1]
D = Q / 'inputs' / 'community'
D.mkdir(parents=True, exist_ok=True)
queries = ['PMP22', 'TEAD', 'YAP', 'NRG1', 'ErbB', 'stiffness', 'coculture', 'GSE201623', 'GSE147285', 'GSE294160', 'density']
for query in queries:
    args = ['./bin/bio', 'community', 'search', '--text', query, '--limit', '100']
    p = subprocess.run(args, capture_output=True, text=True, check=True)
    (D / f'search-{query}.json').write_text(p.stdout)
    data = json.loads(p.stdout)
    print(query, 'total', data['total'], 'next', data['next_offset'])
    for x in data['items']:
        print(' ', x['subject'], x['title'])
for post in ['post_3f7bd6e66753476fb33ec6d9da9cbcc8', 'post_8361a97308264d1892df187d5132826d', 'post_9d25fbe9084740baba1e8b48870d434e', 'post_569bb436329e46828ed286a26425ab03']:
    p = subprocess.run(['./bin/bio', 'community', 'show', post], capture_output=True, text=True, check=True)
    (D / f'{post}.json').write_text(p.stdout)
    print('Saved', post)
