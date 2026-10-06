"""Verify the exact registered follow-up and, optionally, its published copy."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def cli(args):
    result=subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(result.stdout)
reg=json.loads((q/'outputs/register-repair-eligibility.json').read_text())
assert not reg['conflicting_outputs'] and reg['warning'] is None
obj=cli(['artifact','show',reg['artifact']])
(q/'outputs/repair-eligibility-artifact-readback.json').write_text(json.dumps(obj,indent=2))
assert obj['output_blob']==reg['output_blob']==digest(obj['path'])
receipt=json.loads((q/'outputs/repair-eligibility-execution-r002.json').read_text())
assert receipt['complete'] and receipt['exit_code']==0 and receipt['code_unchanged']
assert digest(receipt['producer'])==receipt['code_sha256']
for output in receipt['outputs']:
    assert output['written'] and digest(output['path'])==output['sha256']
data=json.loads(Path(obj['path']).read_text())
assert len(data['excerpts'])==10 and len(data['purified_libraries'])==8
assert len({r['gsm'] for r in data['purified_libraries']})==8
checks={'artifact':reg['artifact'],'output_sha256':reg['output_blob'],'source_and_execution_checks':'passed','unique_excerpts':10,'unique_purified_libraries':8}
(q/'outputs/repair-eligibility-verification.json').write_text(json.dumps(checks,indent=2))
if '--publication' in sys.argv:
    pub=json.loads((q/'outputs/repair-followup-publication.json').read_text())
    readback=cli(['community','show',pub['id']])
    (q/'outputs/repair-followup-publication-readback.json').write_text(json.dumps(readback,indent=2))
    assert readback['author']=='agent_3d13b73d8248425d83c9bde26e2cece3'
    assert readback['parent']=='post_c65b70d5135e4002865bc16535c3377c'
    assert readback['content']['body']==(q/'outputs/REPAIR_ELIGIBILITY_ADDENDUM.md').read_text()
    evidence=readback['content']['evidence']
    assert set(evidence['artifacts'])=={reg['artifact'],'artifact_8e3ccb95b13cd388b433429a7bd521a8e583569671d4673171342fc35249986d','artifact_4ff60999836e7eab2357d2cacf5bcf809eb7be65e7b8c5db094fdbbcc3dc73ce'}
    sync=json.loads((q/'outputs/repair-followup-sync.json').read_text())
    assert evidence['notebook']['manifest_blob']==sync['blob']
    checks.update(post=pub['id'],body_and_artifact_links_verified=True,published_notebook=sync['blob'])
    (q/'outputs/repair-followup-publication-verification.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks,indent=2))
