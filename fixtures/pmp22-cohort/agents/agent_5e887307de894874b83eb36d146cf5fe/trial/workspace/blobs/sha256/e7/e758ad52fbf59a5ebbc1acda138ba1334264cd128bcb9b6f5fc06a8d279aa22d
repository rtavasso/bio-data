"""Read/hash-check published translation audit products; no peer-code execution."""
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
    ('translation-matrix', 'artifact_d300544b5503c962f3a8fb527fd87949c538d290d89ad0fbb6b1af09fdfc46cf'),
    ('translation-blocker', 'artifact_2efa098db8fc682fa7f2d10c1600316616e93ee812623a2be78569a652b84292'),
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
    ('translation-answer', 'post_a42be4e232a54f5bb12a8f837d351455'),
    ('translation-publication', 'post_d7633ba470b24b15b2c0af4712f2edcf'),
]:
    value = cli('community', 'show', post)
    save(label + '-readback.json', value)
    (out / (label + '-body.md')).write_text(value['content']['body'] + '\n')
    print(post, 'superseded_by', value['superseded_by'])
