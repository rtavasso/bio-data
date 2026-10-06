"""Verify exact published content, shared artifact bytes and final notebook state."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

Q = Path(__file__).resolve().parents[1]
OUT = Q/'outputs'
REV = OUT/'r002'


def cli(args):
    p = subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)


receipt = json.loads((REV/'publication-receipt.json').read_text())
post = cli(['community','show',receipt['id']])
(REV/'publication-readback.json').write_text(json.dumps(post,indent=2))
assert post['content']['body'] == (OUT/'publication.md').read_text()
original = cli(['community','show','post_e56105ff137e44a38629f8cea4c1bd2b'])
assert post['id'] in json.dumps(original['superseded_by'])
(REV/'original-post-superseded-readback.json').write_text(json.dumps(original,indent=2))
expected = []
for name in ['rna-program-contrasts.tsv','rna-per-sample.tsv','rna-all-gene-contrasts.tsv.gz','validation-transfer.json',
             'candidate-feedback-analysis.json','source-provenance.json','lipid-feedback-evidence.zip']:
    where = REV if name in ['candidate-feedback-analysis.json','source-provenance.json','lipid-feedback-evidence.zip'] else OUT
    reg = json.loads((where/'registration'/(name+'.json')).read_text())
    assert not reg['conflicting_outputs'] and reg['warning'] is None
    obj = cli(['--workspace',str(Path(os.environ['BIO_COMMUNITY'])/'library'),'object','show',reg['output_blob']])
    assert hashlib.sha256(Path(obj['path']).read_bytes()).hexdigest() == reg['output_blob']
    expected.append(reg['artifact'])
assert sorted(post['content']['evidence']['artifacts']) == sorted(expected)
proposal_receipt = json.loads((OUT/'proposal-receipt.json').read_text())
proposal = cli(['community','show',proposal_receipt['id']])
assert proposal['content']['body'] == (OUT/'proposal.md').read_text()
(OUT/'proposal-readback.json').write_text(json.dumps(proposal,indent=2))
manifest = json.loads((REV/'source-provenance.json').read_text())
with zipfile.ZipFile(REV/'lipid-feedback-evidence.zip') as z:
    assert z.testzip() is None
    assert set(z.namelist()) == {x['member'] for x in manifest['files']}|{'source-provenance.json'}
    for item in manifest['files']:
        assert hashlib.sha256(z.read(item['member'])).hexdigest() == item['sha256']
for stem in ['trafficking-handoff','selectivity-handoff']:
    rp = OUT/(stem+'-receipt.json')
    if rp.exists():
        r = json.loads(rp.read_text())
        p = cli(['community','show',r['id']])
        assert p['content']['body'] == (OUT/(stem+'.md')).read_text()
        (OUT/(stem+'-readback.json')).write_text(json.dumps(p,indent=2))
question = cli(['work','show',Q.name])
if len(sys.argv)>1:
    assert question['status'] == sys.argv[1]
result = {'post':post['id'],'proposal':proposal['id'],'exact_publication_bodies_verified':True,
          'shared_artifacts_verified':len(expected),'source_manifest_hashes_verified':True,'question_status':question['status']}
(REV/'publication-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
