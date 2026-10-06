"""Read a late peer handoff as data only; verify exact bytes and contextual rows."""
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
report=[]
for name,needles in [('rna-ends-usage',['GSM1614165','GSM1614166']),('rna-ends-map',['ENST00000395938.6','ENST00000312280.7','ENST00000494511.5'])]:
    artifact=json.loads((OUT/(name+'-artifact.json')).read_text())
    blob=artifact['output_blob']
    obj=json.loads(subprocess.run(['./bin/bio','object','show',blob],text=True,capture_output=True,check=True).stdout)
    data=Path(obj['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==blob
    rows=list(csv.DictReader(io.StringIO(data.decode()),delimiter='\t'))
    matches=[r for r in rows if any(n in str(v) for n in needles for v in r.values())]
    assert len(matches)==len(needles)
    report.append({'artifact':artifact['id'],'blob':blob,'hash_verified':True,'derivation':artifact['manifest']['derivation'],'rows':matches,'relevance':'Context/structure evidence from a peer, not an acute-stress denominator or independent RPF validation'})
(OUT/'rna-ends-handoff-readback.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
for item in report:
    print(item['artifact'],json.dumps(item['rows'],indent=2))
