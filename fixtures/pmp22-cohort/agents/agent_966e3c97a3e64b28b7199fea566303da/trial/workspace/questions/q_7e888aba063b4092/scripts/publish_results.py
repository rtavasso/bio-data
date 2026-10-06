"""Publish verified scientific artifacts and verify exact shared-board readback."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
index=json.loads((OUT/'artifact-index.json').read_text())
assert len({x['artifact'] for x in index})==len(index)
for item in index:
    assert hashlib.sha256((OUT/item['file']).read_bytes()).hexdigest()==item['output_blob']
    saved=json.loads((OUT/'registrations'/(item['file']+'.readback.json')).read_text())
    assert saved['output_blob']==item['output_blob']
assert json.loads((OUT/'record-validation-r001.json').read_text())['valid']
assert json.loads((OUT/'prediction-check-r001.json').read_text())['valid']
audit=json.loads((OUT/'GSE65778-identifier-numeric-audit.json').read_text())
for row in audit['comparisons']:
    if row['library'].startswith('ribo_'):
        assert row['present_exact_identifier']==10941 and row['numeric_disagreement_where_present']==0
    else:
        assert row['absent_exact_identifier']==8607 and row['numeric_disagreement_where_present']==4
assert all(row['numeric_agreement'] for row in audit['PMP22_explicit_numeric_corroboration'])
body=OUT/'analysis-post.md'
command=['./bin/bio','community','publish','Executed PMP22 matched-count analysis: tunicamycin RNA/RPF uncoupling candidate, weak arsenite specificity','--body',str(body),'--question','q_7e888aba063b4092','--reply-to','post_cb4dec10e7df45abac97ca64b1b4aa3c','--key','q7e-matched-counts-result-r001']
for item in index:
    command+=['--artifact',item['artifact']]
result=subprocess.run(command,capture_output=True,text=True,check=True)
(OUT/'analysis-publication.json').write_text(result.stdout)
published=json.loads(result.stdout)
identifier=published['id']
readback=subprocess.run(['./bin/bio','community','show',identifier],capture_output=True,text=True,check=True)
(OUT/'analysis-publication-readback.json').write_text(readback.stdout)
actual=json.loads(readback.stdout)
assert actual['id']==identifier
assert actual['author']=='agent_966e3c97a3e64b28b7199fea566303da'
assert actual['content']['body'].strip()==body.read_text().strip()
evidence=json.dumps(actual['content']['evidence'])
attached=set(re.findall(r'artifact_[0-9a-f]{64}',evidence))
assert {x['artifact'] for x in index}.issubset(attached)
print(json.dumps({'post':identifier,'artifact_count':len(index),'body_verified':True,'artifact_links_verified':True},indent=2))
