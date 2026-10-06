"""Read back the source-coverage addendum and unchanged historical outputs."""
import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parents[1]
publication = json.loads((q / 'outputs/source-handoff-publication.json').read_text())
result = subprocess.run(['./bin/bio', 'community', 'show', publication['id']], capture_output=True, text=True, check=True)
(q / 'outputs/source-handoff-publication-readback.json').write_text(result.stdout)
post = json.loads(result.stdout)
assert post['content']['body'] == (q / 'SOURCE-HANDOFF-UPDATE.md').read_text()
assert post['parent'] == 'post_3f7bd6e66753476fb33ec6d9da9cbcc8'
expected = {
    'artifact_306fb5726176ef0cce72cbb8e050d575baedd023b6014e8fe674336b16a4c606',
    'artifact_9f094b4877fb0839665160ea6f0ea9811ad84043225962a91a96cbc33dcd1303',
}
assert set(post['content']['evidence']['artifacts']) == expected
work = json.loads((q / 'outputs/source-handoff-work-readback.json').read_text())
assert work['status'] == 'completed'
for artifact in expected:
    assert {'artifact_id': artifact, 'relationship': 'reused'} in work['snapshot']['artifacts']
assert work['snapshot']['files']['LABBOOK.md'] == hashlib.sha256((q / 'LABBOOK.md').read_bytes()).hexdigest()
for product in json.loads((q / 'outputs/registered-products.json').read_text()):
    assert hashlib.sha256((q / 'outputs' / product['file']).read_bytes()).hexdigest() == product['output_blob']
print('VERIFIED_ADDENDUM', post['id'])
print('VERIFIED_WORK', work['id'], work['status'])
print('HISTORICAL_REGISTERED_OUTPUTS_UNCHANGED')
