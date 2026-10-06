import json
import os
import subprocess
from pathlib import Path

q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_90f4fed27b7e4793'
lib = Path(os.environ['BIO_COMMUNITY']) / 'library'

def blob(h):
    return lib / 'blobs/sha256' / h[:2] / h

for name in ['seed-post', 'charter-post']:
    d = json.loads((q / 'outputs' / (name + '.json')).read_text())
    (q / 'outputs' / (name + '.txt')).write_text(json.dumps(d, indent=2))
    if name == 'seed-post':
        print(json.dumps(d, indent=2))
m = json.loads(blob('e054cae33492c105e41221766e86dc067d7c5dfeaf75fc8409c23b468964166b').read_text())
print('NOTEBOOK MANIFEST', json.dumps(m, indent=2))
for aid in ['artifact_0f7ede8968ed0aba576c856ccef0022cb3cdae962cfc1bc2d2f92bd0172b83f9', 'artifact_0ce2aca3b3d0f1f6230aa21d5cd4d5997c63cfeb0dc870e047a34cf245817e7f']:
    raw = subprocess.check_output(['./bin/bio', '--workspace', str(lib), 'artifact', 'show', aid])
    d = json.loads(raw)
    (q / 'outputs' / (aid + '-manifest.json')).write_text(json.dumps(d, indent=2))
    o = json.loads(Path(d['path']).read_text())
    (q / 'outputs' / d['manifest']['output']['name']).write_text(json.dumps(o, indent=2))
    sizes = [blob(i['blob']).stat().st_size for i in d['manifest']['derivation']['inputs']]
    print('ARTIFACT', aid, 'input_bytes', sum(sizes), 'largest', max(sizes))
    print(json.dumps(o, indent=2))
