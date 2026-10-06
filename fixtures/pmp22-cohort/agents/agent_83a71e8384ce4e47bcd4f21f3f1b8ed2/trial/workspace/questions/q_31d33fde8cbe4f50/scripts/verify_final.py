"""Read back exact published state and independently verify key numeric invariants."""
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

q = Path(__file__).resolve().parents[1]
o = q/'outputs'

def bio(args):
    p = subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

reg = json.loads((o/'registrations-final.json').read_text())
pkg = json.loads((o/'package-registration.json').read_text())
expected = {r['artifact'] for r in reg.values()} | {pkg['artifact']}
post_id = json.loads((o/'publication-result.json').read_text())['id']
public = bio(['community','show',post_id])
assert public['content']['body']==(q/'PUBLICATION.md').read_text()
assert public['author']==os.environ['BIO_AGENT']
assert public['parent']=='post_c75060647f604c489d0e8cb6c166bcb4'
assert set(public['content']['evidence']['artifacts'])==expected and len(expected)==14
(o/'publication-readback.json').write_text(json.dumps(public,indent=2))
# Recompute primary fractions directly from frozen native source, not the generated table.
m = json.loads((q/'inputs/frozen-manifest-r001.json').read_text())
h = m['polyasite-human-tpm']['blob']
p = Path(os.environ['BIO_WORKSPACE'])/'blobs/sha256'/h[:2]/h
assert hashlib.sha256(p.read_bytes()).hexdigest()==h
with gzip.open(p,'rt') as f:
    rd = csv.reader(f,delimiter='\t')
    header = next(rd)
    values = {a[3]:list(map(float,a[13:])) for a in rd if a[3] in ['17:15229780:-','17:15230714:-','17:15230826:-']}
assert len(values)==3 and len(header)-13==221
n, passed = 0, 0
for j in range(221):
    den = sum(v[j] for v in values.values())
    if den>=1:
        n += 1
        passed += values['17:15229780:-'][j]/den>=.95
assert (n,passed)==(160,159)
for filename in ['execution-ends-r004.json','execution-extension-r002.json','execution-package-r001.json']:
    r = json.loads((o/filename).read_text())
    assert r['complete'] and r['exit_code']==0
    assert hashlib.sha256(Path(r['producer']).read_bytes()).hexdigest()==r['code_sha256']
    for output in r['outputs']:
        assert output['written'] and hashlib.sha256(Path(output['path']).read_bytes()).hexdigest()==output['sha256']
with zipfile.ZipFile(o/'pmp22-rna-ends-evidence.zip') as z:
    assert z.testzip() is None
    members = len(z.namelist())
for name,args in [('final-inbox',['community','inbox']),('final-sent',['community','inbox','--sent']),('final-work',['work','show',q.name])]:
    result = bio(args)
    (o/(name+'.json')).write_text(json.dumps(result,indent=2))
    if name=='final-work':
        print('WORK',json.dumps(result)[:1500])
verification = {'post':post_id,'artifacts_readback_exact':len(expected),'native_numeric_recheck':[passed,n],'archive_members':members,'archive_bytes':(o/'pmp22-rna-ends-evidence.zip').stat().st_size,'producers_and_outputs_unchanged':True,'package_artifact':pkg['artifact']}
(o/'final-verification.json').write_text(json.dumps(verification,indent=2))
print(json.dumps(verification,indent=2))
