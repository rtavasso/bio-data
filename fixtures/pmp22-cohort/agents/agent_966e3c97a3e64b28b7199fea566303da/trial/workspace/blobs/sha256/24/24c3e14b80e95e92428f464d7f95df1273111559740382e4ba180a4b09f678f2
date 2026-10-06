"""Verify late peer evidence as immutable data; do not rerun the peer screen."""
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
review=[]
for label in ['rbp-peaks','rbp-full-table','rbp-end-containment']:
    manifest=json.loads((OUT/(label+'-artifact.json')).read_text())
    blob=manifest['output_blob']
    obj=json.loads(subprocess.run(['./bin/bio','object','show',blob],capture_output=True,text=True,check=True).stdout)
    data=Path(obj['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==blob
    text=data.decode()
    reader=csv.DictReader(io.StringIO(text),delimiter='\t')
    rows=list(reader)
    selected=[r for r in rows if any(v=='PUM2' for v in r.values())]
    dest=ROOT/'inputs'/'community'/(label+'-notification-evidence.tsv')
    if dest.exists():
        assert dest.read_bytes()==data
    else:
        dest.write_bytes(data)
    record={'label':label,'artifact':manifest['id'],'blob':blob,'hash_verified':True,'derivation':manifest['manifest']['derivation'],'columns':reader.fieldnames,'data_rows':len(rows),'PUM2_rows':selected,'local_evidence':str(dest.relative_to(ROOT)),'attribution':'Peer output inspection, not a new perturbation analysis or evidence of HEK293T occupancy'}
    review.append(record)
    print(label,'rows',len(rows),'columns',reader.fieldnames)
    print(json.dumps(selected,indent=2))
(OUT/'rbp-answer-evidence-review.json').write_text(json.dumps(review,indent=2,allow_nan=False)+'\n')
for file in ['rbp-answer-review.json','rbp-preceding-reply.json','rbp-screen-current.json']:
    post=json.loads((OUT/file).read_text())
    print('POST',post['id'],'SUPERSEDED',post.get('superseded_by'))
    if file=='rbp-preceding-reply.json':
        print(post['content']['body'])
