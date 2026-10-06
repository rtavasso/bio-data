"""Package verified current outputs and exact sources with explicit content hashes."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

q = Path(__file__).resolve().parents[1]
out = q/'outputs'
producer = json.loads((out/'execution-r002.json').read_text())
assert producer['complete'] and producer['exit_code']==0
paths = []
for record in producer['outputs']:
    path = out/Path(record['path']).name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
    paths.append(path)
paths.extend([q/name for name in ['REPORT.md','INDEPENDENT-EVIDENCE.md','REPRODUCE.txt','PROPOSAL.md','analysis-spec.json','LABBOOK.md','HYPOTHESIS-MAP.md']])
paths.extend(sorted((q/'scripts').glob('*.py')))
paths.extend(out/name for name in ['execution-r001.json','execution-r002.json','execution-r002.json.stdout','execution-r002.json.stderr','validation.json','quantitative-review.txt','registered-quantitative-products.json'])
paths.extend([q/'sources'/name for name in ['immutable-inputs.json','additional-primary-inputs.json','native-artifact.json','mapping-artifact.json','samples-artifact.json','bundle-artifact.json','locator-artifact.json','PMC7322568.txt','PMC7430845.txt','literature-candidates.txt','independent-promoter-discovery-europepmc.json','independent-promoter-focused-discovery.json']])
paths.extend(q/'sources'/name for name in ['independent-promoter-focused-retry.json','independent-promoter-retry-details.json','independent-promoter-retry-review.txt'])
source_names = ['GSE139321_Schwann_Cell_Tn5Prime_GEO_Processed.txt','rat-promoter-map.tsv','sample-eligibility.tsv',
                'source-locator-manifest.json','rn5-Pmp22-promoter-sequence.json','rn5-refGene-Pmp22.json',
                'PMC7322568.html','PMC7430845.txt','PMC3100536-bioc.xml','PMC3100536-bioc.txt','PMC3100536-bioc.xml.receipt.json']
paths.extend(q/'sources/inputs'/name for name in source_names)
paths.extend(q/'sources/community'/name for name in ['design-critique-answer.json','design-critique-answer.md','proposal-readback.json','post_c344fef84f344beca27925ec3f9ce940.json','post_162b76b9910c40e39e09f0f033fbadea.json','post_3f7bd6e66753476fb33ec6d9da9cbcc8.json'])
paths = sorted(set(paths))
assert all(p.is_file() for p in paths)
assert shutil.disk_usage(q).free > 5 * sum(p.stat().st_size for p in paths)
manifest = {'question':q.name,'files':[{'path':str(p.relative_to(q)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes':p.stat().st_size} for p in paths],
            'scope':'Selected processed-source evidence and locally authored analysis; no raw reads, executable external code, secrets or full workspace',
            'scientific_receipt':'outputs/execution-r002.json','historical_receipt_note':'r001 is retained history, not the receipt for current registered outputs',
            'script_policy':'Inspect scripts before any reuse; never automatically execute imported code'}
manifest_path = out/'bundle-members.json'
manifest_path.write_text(json.dumps(manifest,indent=2,allow_nan=False))
archive_path = out/'pmp22-promoter-responses.zip'
with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for path in paths:
        archive.write(path,str(path.relative_to(q)))
    archive.write(manifest_path,'outputs/bundle-members.json')
with zipfile.ZipFile(archive_path) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist())==len(paths)+1
    for record in manifest['files']:
        assert hashlib.sha256(archive.read(record['path'])).hexdigest()==record['sha256']
print(json.dumps({'bundle':str(archive_path),'sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),'members':len(paths)+1,'bytes':archive_path.stat().st_size,'roundtrip_verified':True}))
