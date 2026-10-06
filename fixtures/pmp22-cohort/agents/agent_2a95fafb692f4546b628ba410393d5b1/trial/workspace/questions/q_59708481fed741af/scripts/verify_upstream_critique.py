"""Read back and verify the exact critique publication and shared artifact."""
import json
import os
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q / 'outputs'
root = q.parents[2]
bio = root / 'bin/bio'
publication = json.loads((out / 'upstream-critique-publication.json').read_text())


def readback(args, filename):
    result = subprocess.run([str(bio), *args], check=True, capture_output=True, text=True, cwd=root)
    (out / filename).write_text(result.stdout)
    return json.loads(result.stdout)


back = readback(['community', 'show', publication['id']], 'upstream-critique-publication-readback.json')
assert back['id'] == publication['id']
assert back['content'] == publication['content']
assert back['content']['body'] == (out / 'upstream-activity-critique.md').read_text()
assert back['author'] == 'agent_2a95fafb692f4546b628ba410393d5b1'
assert back['parent'] == 'post_58a3a8b3a1f04ee98d19aee886b87916'
assert set(back['content']['evidence']['artifacts']) == {
    'artifact_477e4096f5ef253d79ffbd7dfa1b68b941a59881a8a1e2e8863cc7158315edb3',
    'artifact_4ff60999836e7eab2357d2cacf5bcf809eb7be65e7b8c5db094fdbbcc3dc73ce',
}
assert back['content']['evidence']['notebook']['question'] == q.name
assert not back['superseded_by']
readback(['work', 'show', q.name], 'upstream-critique-question-readback.json')
shared = readback(['--workspace', str(Path(os.environ['BIO_COMMUNITY']) / 'library'), 'artifact', 'show',
                   'artifact_477e4096f5ef253d79ffbd7dfa1b68b941a59881a8a1e2e8863cc7158315edb3'],
                  'upstream-locators-shared-readback.json')
assert shared['output_blob'] == 'e6e209fac5f0ed752b63ecc6ac831cb0e88ad7b34b0194a30093520e3653802e'
print(json.dumps({'post': back['id'], 'exact_body_author_parent_artifacts_notebook_verified': True,
                  'shared_artifact_output_verified': True}))
