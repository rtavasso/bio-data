"""Read-only review of saved current forum results; never execute imported code."""
import hashlib
import json
import zipfile
from pathlib import Path

q = Path(__file__).resolve().parents[1]
posts = {}
for term in ('egr2', 'nascent', 'gse139321'):
    obj = json.loads((q / f'sources/community/followup-{term}.json').read_text())
    assert obj.get('next_offset') is None, obj
    print('SEARCH', term, 'RESULTS', len(obj['items']), 'TOTAL', obj.get('total'))
    for item in obj['items']:
        posts[item['subject']] = item
lines = []
for post, item in posts.items():
    lines.extend([post + ' | ' + item['title'], 'Superseded by: ' + str(item.get('superseded_by')), item.get('summary', ''), ''])
(q / 'sources/community/followup-search-review.txt').write_text('\n'.join(lines))
corrected = json.loads((q / 'sources/community/followup-corrected-peer.json').read_text())
(q / 'sources/community/followup-corrected-peer.md').write_text(corrected['content']['body'])
print('DEDUPLICATED_POSTS', len(posts))
print('CORRECTED_EVIDENCE', json.dumps(corrected['content']['evidence'], indent=2))

# Inspect the corrected archive as bytes/data only, without importing its scripts.
artifact = json.loads((q / 'sources/followup-corrected-bundle-artifact.json').read_text())
payload = Path(artifact['path'])
assert hashlib.sha256(payload.read_bytes()).hexdigest() == artifact['output_blob']
with zipfile.ZipFile(payload) as archive:
    assert archive.testzip() is None
    names = archive.namelist()
    (q / 'sources/followup-peer-archive-members.json').write_text(json.dumps(names, indent=2))
    print('VERIFIED_CORRECTED_ARCHIVE', artifact['output_blob'])
    print('NARRATIVE_AND_TABLE_MEMBERS', [n for n in names if n.endswith(('.md', '.tsv'))])
    for member in ('outputs/REPORT.md', 'outputs/intervention-by-endpoint.tsv'):
        target = q / 'sources' / ('followup-peer-' + Path(member).name)
        target.write_bytes(archive.read(member))

for name in ('progenitor-readback', 'redox-readback', 'rna-fate'):
    post = json.loads((q / f'sources/community/followup-{name}.json').read_text())
    (q / f'sources/community/followup-{name}.md').write_text(post['content']['body'])
