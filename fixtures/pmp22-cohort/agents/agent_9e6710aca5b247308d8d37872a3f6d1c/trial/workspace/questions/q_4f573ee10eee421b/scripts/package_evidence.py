"""Package exact scoped evidence; archive creation is not new scientific replication."""
import hashlib
import json
import zipfile
from pathlib import Path

Q = Path(__file__).resolve().parents[1]
W = Q.parents[1]
OUT = Q/'outputs'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

paths={Q/'LABBOOK.md',Q/'QUESTION.md'}
for root in [Q/'inputs',Q/'scripts',OUT]:
    for path in root.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        if path.name.startswith(('package-execution','bundle-manifest','mechanics-evidence','publication-readback','publication-verification')):
            continue
        if path.name.endswith('.pyc'):
            continue
        paths.add(path)
manifest=json.loads((Q/'inputs/acquisition/manifest.json').read_text())
paths.update(W/x['path'] for x in manifest)
for digest in ['98071053e11e1b5a7feaf41d5b76e30cba8e1a7cb2aefdd2287557429054a6b0','ebe8a69f76a005dbf03854069a4c67429dd47c1cfc44d2255ba97e99348437f0','b0bacee055ff8103e1d6d0b6f58e04bebbe19e2285f95b33d0577133170e4304']:
    paths.add(W/'blobs/sha256'/digest[:2]/digest)
paths.update([Q.parent/'q_e835197734394f30/inputs/primary/GSE79115-samples.soft',Q.parent/'q_e835197734394f30/inputs/primary/PMC4925303.txt'])
rows=[]
with zipfile.ZipFile(OUT/'mechanics-evidence.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
    for path in sorted(paths,key=str):
        assert path.is_relative_to(W) and not path.is_symlink()
        rel=str(path.relative_to(W))
        digest=sha(path)
        row={'workspace_path':rel,'sha256':digest,'bytes':path.stat().st_size}
        rows.append(row)
        z.write(path,rel,compress_type=zipfile.ZIP_STORED if 'blobs' in path.parts else zipfile.ZIP_DEFLATED)
with zipfile.ZipFile(OUT/'mechanics-evidence.zip') as z:
    assert z.testzip() is None
    assert set(z.namelist())=={x['workspace_path'] for x in rows}
    for row in rows:
        with z.open(row['workspace_path']) as f:
            assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
result={'members':rows,'archive_sha256':sha(OUT/'mechanics-evidence.zip'),'archive_bytes':(OUT/'mechanics-evidence.zip').stat().st_size,'member_count':len(rows),'all_member_hashes_verified':True,'scope':'selective pre-publication evidence snapshot; archive construction only, no scientific recomputation'}
(OUT/'bundle-manifest.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='members'},indent=2))
