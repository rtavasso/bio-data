"""Verify published final evidence, exact author/body/links and current producer hashes."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
post=json.loads((OUT/'final-publication-readback.json').read_text())
assert post['id']=='post_d2aa0d7e935f4cabbe60af1494dda5dd'
assert post['author']=='agent_658d8df4f8694638ae0a1b33cb42ab44'
assert post['parent']=='post_910fc4d8914a4a32ae441c8481e020c7'
assert post['content']['body']==(OUT/'final-analysis-post.md').read_text()
assert post['content']['evidence']['notebook']['question']==ROOT.name
expected=set()
for role in ['REPORT','candidate-contrast-table','robustness-grid','novelty-validation-audit','uncertainty-map','independent-checks','source-locators']:
    r=json.loads((OUT/'registrations-final'/(role+'.json')).read_text())
    expected.add(r['artifact'])
assert set(post['content']['evidence']['artifacts'])==expected
question=json.loads((OUT/'final-question-readback.json').read_text())
print('question status:',question.get('status'))
assert question['id']==ROOT.name and question['status']=='completed'
for name,body in [('parent-completion-readback.json','parent-completion.md'),('lipid-completion-readback.json','lipid-completion.md')]:
    peer=json.loads((OUT/name).read_text())
    assert peer['author']==post['author']
    assert peer['content']['body']==(OUT/body).read_text()
verified=[]
for name in ['execution-r002.json','verification-execution-r001.json','synthesis-execution-r002.json']:
    r=json.loads((OUT/name).read_text())
    assert r['complete'] and r['exit_code']==0 and r['code_unchanged']
    assert hashlib.sha256(Path(r['producer']).read_bytes()).hexdigest()==r['code_sha256']
    for item in r['outputs']:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
    verified.append({'receipt':name,'outputs':len(r['outputs']),'producer_unchanged':True})
result={'publication':post['id'],'author_body_parent_links_verified':True,'linked_artifacts':len(expected),'receipts':verified,'endpoint_rows':json.loads((OUT/'report-validation.json').read_text())['endpoint_rows'],'question_readback_saved':'final-question-readback.json','valid':True}
(OUT/'final-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
