"""Compact evidence audit for primary sources, sample maps and native containers."""
import json
import subprocess
import zipfile
from pathlib import Path
from defusedxml import ElementTree as ET
q = Path(__file__).resolve().parents[1]
ws = q.parents[1]

def blob(h):
    return ws / 'blobs/sha256' / h[:2] / h

for term in ['phosphatase','hdac3','ubiquitin']:
    d = json.loads((q/f'outputs/{term}-metadata.json').read_text())
    print(term, 'total', d.get('total'), 'items', [(i.get('id'), i.get('title'), i.get('subject'), i.get('name')) for i in d.get('items', [])])
p = ws/'questions/q_59708481fed741af/outputs/prior-package.pretty.json'
package = json.loads(p.read_text())
for group in ['input_objects', 'files', 'objects']:
    for r in package.get(group, []):
        name = r['path']
        if name.endswith('.xml') or any(t in name for t in ['Figlia', 'nae1-RNA-summary', 'PRJEB20661-samples', 'sample-map']):
            print('INHERITED', name, r['sha256'])
            if name.endswith('.xml') and blob(r['sha256']).exists():
                try:
                    root = ET.fromstring(blob(r['sha256']).read_bytes())
                except ET.ParseError as error:
                    print('NON_XML_SOURCE_SKIPPED', r['sha256'], str(error))
                    continue
                title = root.find('.//article-title')
                print('TITLE', ''.join(title.itertext()) if title is not None else None)
d = json.loads((q/'outputs/tead-source-fetch.json').read_text())
print('TEAD_FETCH', d)
if d.get('blob'):
    with zipfile.ZipFile(blob(d['blob'])) as z:
        print('TEAD_MEMBERS', [(i.filename, i.file_size) for i in z.infolist()])
d = json.loads(blob('2aa166f06f67fb37c49b65f5b659bd9213d8dc290984183f7cd0d074bff34813').read_text())
for key, v in d.items():
    print('NRG_SAMPLE', key, {k:v.get(k) for k in ['Sample_title','Sample_description','Sample_treatment_protocol_ch1','Sample_extract_protocol_ch1','Sample_data_processing']})
post = json.loads((q/'outputs/proposal-post.json').read_text())
id_ = post['id']
r = subprocess.run(['./bin/bio','community','show',id_], capture_output=True, text=True, check=True)
(q/'outputs/proposal-readback.json').write_text(r.stdout)
assert json.loads(r.stdout)['content']['body'] == (q/'outputs/early-proposal.md').read_text()
print('PROPOSAL_VERIFIED', id_)
