"""Read back exact community post and verify its published evidence links."""

import json
import os
import subprocess
from pathlib import Path
q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_90f4fed27b7e4793'
pub = json.loads((q / 'outputs/community-publication.json').read_text())
print('Publication response fields:', list(pub))
post = pub['id']
r = subprocess.run(['./bin/bio', 'community', 'show', post], capture_output=True, text=True, check=True)
(q / 'outputs/community-publication-readback.json').write_text(r.stdout)
readback = json.loads(r.stdout)
print('Readback fields:', list(readback))
assert readback['id'] == post
assert readback['content'] == pub['content']
assert readback['content']['body'] == (q / 'COMMUNITY_ANALYSIS.md').read_text()
# The exact post must be in the readback; preserve its complete response for review.
assert post in r.stdout
for item in json.loads((q / 'outputs/artifact-index.json').read_text()):
    assert item['artifact'] in r.stdout
print(json.dumps({'post': post, 'content_blob_sha256': pub['body_blob'], 'readback_verified': True,
                  'evidence': readback['content']['evidence']}, indent=2, allow_nan=False))
