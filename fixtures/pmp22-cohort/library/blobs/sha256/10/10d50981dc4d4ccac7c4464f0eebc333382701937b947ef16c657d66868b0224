"""Read selected text members only; never execute inherited scientific code."""
import hashlib
import json
import os
import zipfile
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_90f4fed27b7e4793'
w=Path(os.environ['BIO_WORKSPACE'])
out=q/'inputs/prior';out.mkdir(parents=True,exist_ok=True)
d=json.loads((q/'outputs/artifact_0f7ede8968ed0aba576c856ccef0022cb3cdae962cfc1bc2d2f92bd0172b83f9-manifest.json').read_text())
receipts=[]
names={'antioxidant-eligibility.tsv','antioxidant-source-mapping.json','antioxidant-gene-effects.tsv','antioxidant-posthoc-summary.json'}
for x in d['manifest']['derivation']['inputs']:
    h=x['blob'];p=w/'blobs/sha256'/h[:2]/h
    with p.open('rb') as f:magic=f.read(4)
    if magic[:2]!=b'PK':continue
    with zipfile.ZipFile(p) as z:
        chosen=[n for n in z.namelist() if Path(n).name in names]
        print(h,p.stat().st_size,'members',len(z.namelist()),'selected',chosen)
        for n in chosen:
            assert z.getinfo(n).file_size<1000000
            data=z.read(n);target=out/Path(n).name
            assert not target.exists() or target.read_bytes()==data
            target.write_bytes(data)
            receipts.append({'parent_blob':h,'member':n,'output':str(target.relative_to(q)),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
(out/'extraction-receipts.json').write_text(json.dumps(receipts,indent=2,allow_nan=False))
print('EXTRACTED',len(receipts))
