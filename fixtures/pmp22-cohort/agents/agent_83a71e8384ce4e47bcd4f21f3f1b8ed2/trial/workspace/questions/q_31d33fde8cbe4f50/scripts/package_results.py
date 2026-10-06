"""Package final tables, code, notes and receipts; source measurements remain immutable inputs."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

q = Path(__file__).resolve().parents[1]
o = q / 'outputs'
assert shutil.disk_usage(q).free > 5368709120
reg = json.loads((o / 'registrations-final.json').read_text())
files = [q/'REPORT.md', q/'LABBOOK.md', q/'PROPOSAL.md', q/'ASK-PUM2-FOLLOWUP.md', q/'inputs/frozen-manifest-r001.json', q/'inputs/extension-manifest.json', o/'registrations-final.json', o/'predictions/mir29-retention-r001.json']
for name, r in reg.items():
    p = o / name
    assert hashlib.sha256(p.read_bytes()).hexdigest() == r['output_blob']
    files.append(p)
files.extend(sorted((q/'scripts').glob('*.py')))
files.extend(sorted(o.glob('execution-ends-*.json*')))
files.extend(sorted(o.glob('execution-extension-*.json*')))
files.extend(sorted((q/'inputs/sources').glob('*.receipt.json')))
files.extend(sorted((q/'inputs/prior').glob('*checkpoint.json')))
files.extend(sorted((q/'inputs/prior').glob('forum-PUM2-checkpoint.json')))
files = sorted(set(files))
records = [{'path':str(p.relative_to(q)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes':p.stat().st_size} for p in files]
manifest = {'question':q.name,'members':records,'source_bytes_policy':'Native measurement and source bytes are explicit registered derivation inputs, not duplicated in this compact ZIP. community fetch retrieves the immutable input closure. No raw reads or downloaded code execution.','final_core_receipt':'execution-ends-r004.json','final_extension_receipt':'execution-extension-r002.json','superseded_outputs':'Earlier failed/draft receipt hashes are retained; final tables correspond only to final receipts.'}
mp = o/'package-manifest.json'
mp.write_text(json.dumps(manifest,indent=2))
zp = o/'pmp22-rna-ends-evidence.zip'
with zipfile.ZipFile(zp,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p,str(p.relative_to(q)))
    z.write(mp,'outputs/package-manifest.json')
with zipfile.ZipFile(zp) as z:
    assert z.testzip() is None
    assert len(z.namelist()) == len(records)+1
    for r in records:
        b = z.read(r['path'])
        assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
    assert z.read('outputs/package-manifest.json')==mp.read_bytes()
print(json.dumps({'zip':str(zp),'members':len(records)+1,'bytes':zp.stat().st_size,'sha256':hashlib.sha256(zp.read_bytes()).hexdigest(),'verified':True}))
