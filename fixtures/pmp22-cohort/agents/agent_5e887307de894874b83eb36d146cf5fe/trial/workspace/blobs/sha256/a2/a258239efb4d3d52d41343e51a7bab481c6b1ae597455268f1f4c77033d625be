"""Read/hash-check small shared cis-audit products without rerunning peer analyses."""
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
    ('cis-evidence', 'artifact_c29f4ea4bba4c049e5387ad507ab14d3a25699b80017b0896bcca3bb62114f48'),
    ('cis-rat-map', 'artifact_46c490850c14f6afe9d32cb74b32ad94e60d828de0751236d25c51fcc079771a'),
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
    ('cis-answer', 'post_0cea3feab3c14c07bf8363614a411288'),
    ('cis-publication', 'post_3f7bd6e66753476fb33ec6d9da9cbcc8'),
    ('cis-egr2-handoff', 'post_6026be202645480694b16fe46884fa53'),
]:
    value = cli('community', 'show', post)
    save(label + '-readback.json', value)
    (out / (label + '-body.md')).write_text(value['content']['body'] + '\n')
    print(post, 'superseded_by', value['superseded_by'])
