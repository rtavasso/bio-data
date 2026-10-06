"""Read exact peer output blobs and derivations as data only."""
import hashlib
import json
import subprocess
from pathlib import Path

R=Path(__file__).resolve().parents[1]
report=[]
for label in ['parent','rbp-peaks']:
    a=json.loads((R/'outputs'/(label+'-artifact.json')).read_text())
    blob=a['output_blob']
    m=json.loads(subprocess.run(['./bin/bio','object','show',blob],capture_output=True,text=True,check=True).stdout)
    data=Path(m['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==blob
    dest=R/'inputs'/'community'/(label+'-output')
    dest.write_bytes(data)
    d=a['manifest']['derivation']
    report.append({'label':label,'artifact':a['id'],'blob':blob,'hash_verified':True,'derivation':d,'output_local':str(dest)})
    print(label,'blob',blob,'bytes',len(data),'derivation_fields',list(d))
    print(data[:12000].decode())
(R/'outputs'/'peer-evidence-readback.json').write_text(json.dumps(report,indent=2)+'\n')
