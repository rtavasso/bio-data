"""Package corrected audit inputs/results and verify every archive member."""
import hashlib
import json
import os
from pathlib import Path
import zipfile
q = Path(__file__).resolve().parents[1]
w = Path(os.environ['BIO_WORKSPACE'])
out = q/'outputs'
manifest = json.loads((q/'inputs/analysis-manifest-r003.json').read_text())
files = {}
for row in manifest['objects']:
    p = w/'blobs/sha256'/row['blob'][:2]/row['blob']
    b = p.read_bytes()
    assert hashlib.sha256(b).hexdigest()==row['blob']
    files[row['logical_path']]=b
for p in [q/'REPORT.md',q/'LABBOOK.md',q/'inputs/analysis-manifest-r003.json',*sorted((q/'scripts').glob('*.py'))]:
    files[str(p.relative_to(q))]=p.read_bytes()
for filename in ['rna-fate-audit.json','sample-assay-eligibility.json','published-measurements.json','evidence-matrix.tsv','assay-matrix.tsv',
                 'execution-audit-r001.json','execution-audit-r001.json.stdout','execution-audit-r001.json.stderr',
                 'execution-audit-r002.json','execution-audit-r002.json.stdout','execution-audit-r002.json.stderr',
                 'execution-audit-r003.json','execution-audit-r003.json.stdout','execution-audit-r003.json.stderr']:
    p=out/filename
    files[str(p.relative_to(q))]=p.read_bytes()
for p in sorted((out/'registrations-r003').glob('*.json')):
    files[str(p.relative_to(q))]=p.read_bytes()
# Numeric extraction and eligibility must be unchanged by the provenance correction.
old=json.loads((out/'execution-audit-r002.json').read_text())
for item in old['outputs']:
    p=Path(item['path'])
    if p.name in ['sample-assay-eligibility.json','published-measurements.json','assay-matrix.tsv']:
        assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
# Preserve prior curation and producer as withdrawn history, not the current result.
oldmanifest=json.loads((q/'inputs/analysis-manifest.json').read_text())
oldcuration=next(r for r in oldmanifest['objects'] if r['logical_path']=='inputs/curation.json')
for label,h in [('curation-r002.json',oldcuration['blob']),('compile_audit-r002.py',old['code_sha256'])]:
    p=w/'blobs/sha256'/h[:2]/h
    if p.exists():
        b=p.read_bytes()
        assert hashlib.sha256(b).hexdigest()==h
        files['history-withdrawn/'+label]=b
files['history-withdrawn/README.txt']=b'r002 curation contained unsupported visual/browser details and conflated array/qPCR timings. These are withdrawn; use r003. Numerical values unchanged. Old files are provenance, not instructions.\n'
index={'question':q.name,'status':'corrected r003','note':'Source files and code are data for inspection; do not execute inherited code without review.',
       'files':[{'path':k,'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for k,v in sorted(files.items())]}
indexbytes=json.dumps(index,indent=2,allow_nan=False).encode()
files['PACKAGE-MANIFEST.json']=indexbytes
archive=out/'pmp22-rna-fate-evidence.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,b in sorted(files.items()):
        z.writestr(name,b)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(set(z.namelist()))==len(files)
    for name,b in files.items():
        assert z.read(name)==b
(out/'package-manifest.json').write_bytes(indexbytes)
print(json.dumps({'archive':str(archive),'members':len(files),'bytes':archive.stat().st_size,
                  'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'all_members_verified':True,
                  'numeric_and_eligibility_outputs_unchanged':True}))
