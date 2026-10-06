"""Review small published proteostasis artifacts; no scientific reanalysis or network retrieval."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

out = Path(__file__).resolve().parents[1] / 'outputs'
lib = str(Path(os.environ['BIO_COMMUNITY']) / 'library')


def cli(*args):
    return json.loads(subprocess.check_output(['./bin/bio', *args], text=True))


def save(name, value):
    (out / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


for label, aid in [('proteostasis-disposition', 'artifact_87fa9f1eca8180a7f98c6bf0f2b2a69596b82c835cd54ab988586c76eba6d0a1'),
                   ('proteostasis-design', 'artifact_361eb0933af8a2a9bd032eeca7e30e7c6cc492fe16961bc713396eba55facbb4')]:
    a = cli('--workspace', lib, 'artifact', 'show', aid)
    save(label + '-review-manifest.json', a)
    path = Path(a['path'])
    assert path.stat().st_size < 150_000
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == a['output_blob']
    copy = out / (label + '-reviewed' + Path(a['manifest']['output']['name']).suffix)
    copy.write_bytes(data)
    print(aid, len(data), 'bytes; hash verified;', copy)
for label, post in [('proteostasis-answer', 'post_95e40197945548b58bc903a72e1d9b70'),
                    ('proteostasis-publication', 'post_ede3429c8d7a4485b7681fbf94798066')]:
    value = cli('community', 'show', post)
    save(label + '-readback.json', value)
    print(post, 'superseded_by', value['superseded_by'])
