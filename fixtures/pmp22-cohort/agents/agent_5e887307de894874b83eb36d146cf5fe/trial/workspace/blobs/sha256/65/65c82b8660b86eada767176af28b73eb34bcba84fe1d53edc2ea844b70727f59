"""Inspect small published RNA-fate evidence; no primary retrieval or peer-code execution."""
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


for aid in [
    'artifact_1d6755f53dee3b9706684da0a5bae1f5658430b169a0fdcab9d908f6548d2823',
    'artifact_9e67145453cb9dece8ac3f9de3ec3cc03ede0f1206b67669844cea1db56affa6',
    'artifact_3286210538560e5134205623795d82d209e16123d47f1eed5aae248009f10f41',
    'artifact_73ccbb50388d90cef6493aeb0bf8116f27035f9d5d89e211e41e55fdf7f5a6fa',
    'artifact_882bd250c232e55f8c377e3c895353fe414351297a3fbd9b76a4483d8874f486',
]:
    a = cli('--workspace', lib, 'artifact', 'show', aid)
    name = a['manifest']['output']['name']
    assert Path(name).name == name
    save('rna-fate-' + name + '-manifest.json', a)
    path = Path(a['path'])
    if path.stat().st_size >= 150_000 or Path(name).suffix not in {'.tsv', '.json', '.md', '.csv'}:
        print(aid, name, 'manifest only')
        continue
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == a['output_blob']
    copy = out / ('rna-fate-reviewed-' + name)
    copy.write_bytes(data)
    print(aid, a['manifest']['title'], len(data), 'bytes; hash verified;', copy.name)
for label, post in [
    ('rna-fate-answer', 'post_1638197dea584271b7c8bd8af6016f57'),
    ('rna-fate-publication', 'post_1b2c4f75fb614dd7931820b681db11d7'),
]:
    value = cli('community', 'show', post)
    save(label + '-readback.json', value)
    (out / (label + '-body.md')).write_text(value['content']['body'] + '\n')
    print(post, 'superseded_by', value['superseded_by'])
