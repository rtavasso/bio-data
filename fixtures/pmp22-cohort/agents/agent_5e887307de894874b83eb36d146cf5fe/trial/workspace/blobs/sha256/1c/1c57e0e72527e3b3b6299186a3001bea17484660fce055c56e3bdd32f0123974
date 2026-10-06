"""Inspect small shared lipid/endocrine audit products; no scientific reanalysis."""
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
    ('lipid-endpoint', 'artifact_eefcd493a7872cd9f1c9da722ef0e88fa5d5464ad2f05c9a5cbe21b5e2350478'),
    ('lipid-bidirectionality', 'artifact_ceb81792b1f236aa1993a55910b97c06ca077514e2f08da622895ab93a47fa87'),
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
    ('lipid-answer', 'post_07972ef0c59c40b293bf399eac5f429d'),
    ('lipid-publication', 'post_78aab10c0b084ef89511249f43fe0180'),
]:
    value = cli('community', 'show', post)
    save(label + '-readback.json', value)
    (out / (label + '-body.md')).write_text(value['content']['body'] + '\n')
    print(post, 'superseded_by', value['superseded_by'])
