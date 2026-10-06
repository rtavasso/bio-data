"""Read-only local evidence inventory; never execute inherited code or acquire data."""
import json
import os
import subprocess
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
OUT = Q / 'outputs' / 'evidence'
OUT.mkdir(parents=True, exist_ok=True)
LIB = str(Path(os.environ['BIO_COMMUNITY']) / 'library')

def cli(*args):
    return json.loads(subprocess.check_output(['./bin/bio', *args], text=True))

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')

seed = cli('community', 'show', 'post_9d25fbe9084740baba1e8b48870d434e')
save('seed-post.json', seed)
save('baseline-board.json', cli('community', 'audit'))
for label, blob in [('notebook-manifest', seed['content']['evidence']['notebook']['manifest_blob']),
                    ('evidence-manifest', seed['content']['evidence']['manifest_blob'])]:
    record = cli('--workspace', LIB, 'object', 'show', blob)
    value = json.loads(Path(record['path']).read_text())
    save(label + '.json', value)
    print(label, 'keys', list(value))
    if label == 'notebook-manifest':
        book = cli('--workspace', LIB, 'object', 'show', value['files']['LABBOOK.md'])
        save('notebook-location.json', book)
        print('LABBOOK', book['path'])
summary = []
for aid in seed['content']['evidence']['artifacts']:
    art = cli('--workspace', LIB, 'artifact', 'show', aid)
    save(aid + '.json', art)
    summary.append({k: art[k] for k in ['id', 'path', 'output_blob'] } | {
        'title': art['manifest']['title'], 'output': art['manifest']['output'],
        'summary': art['manifest']['summary']})
save('artifact-index.json', summary)
for item in summary:
    print(item['id'], item['output']['name'], item['output']['bytes'], item['output_blob'])
