"""Verify the follow-up's actual catalog readbacks and unchanged prior outputs."""
import hashlib
import json
from pathlib import Path

q = Path(__file__).resolve().parents[1]
peer = 'artifact_13cc1c9191396833d1c76cb016bdf9702f312f5a8e285c852a8ac3a5c442b42c'
work = json.loads((q / 'outputs/followup-work-readback.json').read_text())
sync = json.loads((q / 'outputs/followup-sync.json').read_text())
artifact = json.loads((q / 'outputs/followup-peer-use-readback.json').read_text())
assert work['id'] == 'q_e9e29d6eed344964'
assert work['status'] == 'completed'
assert work['current_work'] == 'work_' + sync['blob']
assert {'artifact_id': peer, 'relationship': 'reused'} in work['snapshot']['artifacts']
assert {'question_id': work['id'], 'relationship': 'reused'} in artifact['questions']
assert work['snapshot']['files']['LABBOOK.md'] == hashlib.sha256((q / 'LABBOOK.md').read_bytes()).hexdigest()
products = json.loads((q / 'outputs/registered-products.json').read_text())
for product in products:
    assert hashlib.sha256((q / 'outputs' / product['file']).read_bytes()).hexdigest() == product['output_blob']
result = {
    'passed': True,
    'status': work['status'],
    'notebook_snapshot': work['current_work'],
    'corrected_peer_archive_reused': peer,
    'unchanged_preexisting_products': [p['artifact'] for p in products],
    'note_local_path': str(q / 'EGR2-FOLLOWUP.md'),
    'note_itself_in_snapshot': 'EGR2-FOLLOWUP.md' in work['snapshot']['files'],
    'scope': 'Narrative follow-up; notebook summary synced, root note retained locally; no new raw processing or computation registration',
}
(q / 'outputs/followup-validation.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
print(json.dumps(result, indent=2, allow_nan=False))
