"""Review small extrinsic-input artifacts and current handoffs without scientific reruns."""
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


for label, aid in [
    ('axon-array-summary', 'artifact_145db00d71615596a413ff7301f480834996697fbe55ad3580182e0e7f294663'),
    ('axon-assay-eligibility', 'artifact_3299f8025adff625c3d0e473866cd8f408ad8c046220869e9a02e1997ad5c89c'),
]:
    a = cli('--workspace', lib, 'artifact', 'show', aid)
    save(label + '-review-manifest.json', a)
    path = Path(a['path'])
    assert path.stat().st_size < 150_000
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == a['output_blob']
    copy = out / (label + '-reviewed' + Path(a['manifest']['output']['name']).suffix)
    copy.write_bytes(data)
    print(aid, len(data), 'bytes; hash verified;', copy.name)
for label, post in [
    ('axon-answer', 'post_dd0dc78960284b3fb091a163e3b2082b'),
    ('axon-publication', 'post_ecc13cabecf54b789e538f695e4bdca2'),
    ('axon-cis-source-update', 'post_162b76b9910c40e39e09f0f033fbadea'),
]:
    value = cli('community', 'show', post)
    save(label + '-readback.json', value)
    (out / (label + '-body.md')).write_text(value['content']['body'] + '\n')
    print(post, 'superseded_by', value['superseded_by'])
