"""Produce a verified analysis bundle, with native sources referenced by blob hash."""
from pathlib import Path
import json,hashlib,tarfile
Q=Path(__file__).resolve().parents[1];O=Q/'outputs'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=[Q/'LABBOOK.md',Q/'QUESTION.md']+sorted((Q/'scripts').glob('*.py'))
files+=sorted(p for p in O.rglob('*') if p.is_file() and '__pycache__' not in p.parts and not p.name.startswith(('package-','final-handoff-')))
files+=sorted(p for p in (Q/'inputs').rglob('*') if p.is_file() and p.suffix in ['.json','.soft','.xml','.html','.stderr'])
files=list(dict.fromkeys(files));assert all(p.is_file() for p in files)
records=[dict(path=str(p.relative_to(Q)),sha256=sha(p),bytes=p.stat().st_size) for p in files]
manifest=dict(question=Q.name,archive='outputs/package-analysis.tar.gz',members=records,member_count=len(records),source_bytes='Native count/matrix/workbook bytes remain immutable workspace blobs referenced in acquisition receipts; archive includes derived matrices and source text, not all native data.',scientific_status='Bounded reference sensitivity; causal cell identity/NRF2 mediation unresolved; see REPORT and evidence-index',execution='This script aggregates existing genuine outputs; it is not the producer of their original scientific computations. Their own execution receipts are included.')
(O/'package-manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
with tarfile.open(O/'package-analysis.tar.gz','w:gz') as t:
 for p in files:t.add(p,arcname=str(p.relative_to(Q)),recursive=False)
 t.add(O/'package-manifest.json',arcname='outputs/package-manifest.json',recursive=False)
# Read archive entries without extraction or execution; verify exact bytes.
with tarfile.open(O/'package-analysis.tar.gz','r:gz') as t:
 assert len(t.getmembers())==len(files)+1
 for r in records:
  member=t.getmember(r['path']);assert member.isfile();f=t.extractfile(member);assert hashlib.sha256(f.read()).hexdigest()==r['sha256']
print(json.dumps(dict(archive=str(O/'package-analysis.tar.gz'),members=len(records)+1,bytes=(O/'package-analysis.tar.gz').stat().st_size,sha256=sha(O/'package-analysis.tar.gz'),all_member_hashes_verified=True),indent=2))
