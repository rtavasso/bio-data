"""Package only this question's saved evidence; no scientific recomputation."""
import hashlib
import json
from pathlib import Path
import zipfile
Q=Path(__file__).resolve().parents[1]
OUT=Q/'outputs'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

paths=[Q/'LABBOOK.md',Q/'QUESTION.md']
paths+=sorted(p for p in (Q/'inputs').rglob('*') if p.is_file())
paths+=sorted(p for p in (Q/'scripts').glob('*.py'))
paths+=sorted(p for p in OUT.iterdir() if p.is_file() and p.suffix in ('.json','.tsv','.md','.stdout','.stderr') and not p.name.startswith(('package-','bundle-')))
paths+=sorted(p for p in (OUT/'registrations').glob('*.json') if not p.name.startswith('extrinsic-evidence'))
# Include the original naming-only validator version as an immutable historical code file.
old=Q.parents[1]/'blobs/sha256/4c/4cdaac33fde52332505e196ffb809b2934650127a778a500cc7c4e063cb8122b'
manifest={'question':'q_e835197734394f30','scope':'Question-local evidence, source bytes, existing results, authored interpretation and proposed test; packaging is not independent replication','members':[]}
for p in paths:
    assert p.resolve().is_relative_to(Q.resolve())
    manifest['members'].append({'path':str(p.relative_to(Q)),'bytes':p.stat().st_size,'sha256':sha(p)})
archive=OUT/'extrinsic-evidence.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in paths:
        z.write(p,str(p.relative_to(Q)))
    z.writestr('historical-code/validate_and_compile-r001.py',old.read_bytes())
    manifest['historical_code']={'name':'historical-code/validate_and_compile-r001.py','sha256':sha(old),'source_blob':old.name}
    z.writestr('bundle-manifest.json',json.dumps(manifest,indent=2,allow_nan=False)+'\n')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for r in manifest['members']:
        data=z.read(r['path'])
        assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256']
manifest['archive']={'bytes':archive.stat().st_size,'sha256':sha(archive),'zip_members_verified':len(manifest['members'])+2}
(OUT/'bundle-manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
print(json.dumps(manifest['archive'],indent=2))
