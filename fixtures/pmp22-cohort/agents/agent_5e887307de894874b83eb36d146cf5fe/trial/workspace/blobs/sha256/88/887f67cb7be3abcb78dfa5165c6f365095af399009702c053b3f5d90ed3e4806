"""Bounded read-only review of already published peer evidence; no analysis rerun."""
import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
for stem in ['redox-causal-audit', 'redox-epistasis']:
    artifact = json.loads((out / (stem + '-manifest.json')).read_text())
    path = Path(artifact['path'])
    assert path.stat().st_size < 150_000
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == artifact['output_blob']
    dest = out / (stem + '-reviewed' + Path(artifact['manifest']['output']['name']).suffix)
    dest.write_bytes(data)
    print(json.dumps({'artifact': artifact['id'], 'bytes': len(data), 'review_copy': str(dest),
                      'output_hash_verified': True, 'summary': artifact['manifest']['summary']}))
for slug, post in [('redox-analysis', 'post_ea592203d52c44aba1f05d4af668012c'),
                   ('regulator-provenance-correction', 'post_8361a97308264d1892df187d5132826d'),
                   ('state-compartment-update', 'post_c65b70d5135e4002865bc16535c3377c')]:
    value = json.loads(subprocess.check_output(['./bin/bio', 'community', 'show', post], text=True))
    (out / (slug + '-readback.json')).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    (out / (slug + '-body.md')).write_text(value['content']['body'])
    print(post, 'superseded_by', value['superseded_by'], 'saved', slug)
