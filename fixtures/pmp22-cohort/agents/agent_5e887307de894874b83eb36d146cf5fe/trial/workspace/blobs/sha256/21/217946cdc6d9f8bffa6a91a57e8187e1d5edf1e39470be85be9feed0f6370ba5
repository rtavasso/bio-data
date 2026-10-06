"""Review small human-dosage audit products; no scientific reanalysis or imported code."""
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
    ('human-dosage-matrix', 'artifact_ebe9b1c68c7032205edb8f19443706961ef33bb5050b68afa98e09cf1e67b9d3'),
    ('human-dosage-verification', 'artifact_71f6aed6aa2445d419d10b5ac4d4fe87644b12c75e9ecb43cd04796985c0b953'),
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
    ('human-dosage-answer', 'post_4a2fa7cfd64e4909a273525fea8898b8'),
    ('human-dosage-publication', 'post_a28905a9965a474789714990f586078b'),
]:
    value = cli('community', 'show', post)
    save(label + '-readback.json', value)
    (out / (label + '-body.md')).write_text(value['content']['body'] + '\n')
    print(post, 'superseded_by', value['superseded_by'])
