"""Build a bounded native-source bundle and really replay three authored analyses."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

Q=Path(__file__).resolve().parents[1]
WS=Q.parents[1]
OUT=Q/'outputs'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

environment={'python':sys.version,'packages':{name:importlib.metadata.version(name) for name in ['numpy','pandas','scipy','openpyxl','matplotlib','defusedxml']}}
(OUT/'analysis-environment.json').write_text(json.dumps(environment,indent=2)+'\n')
blobs=set()
for name in ['executed-contrasts.json','followup-contrasts.json']:
    blobs.update(json.loads((OUT/name).read_text())['input_blobs'])
for p in OUT.glob('*-fetch.json'):
    d=json.loads(p.read_text())
    if isinstance(d,dict) and d.get('blob'):
        blobs.add(d['blob'])
# Previously preserved and independently inspected primary TEAD1 source text.
blobs.add('11c2558cb6e86ddacce2abf86289f86e1dd8981edb4d08db18849d7cca14031c')
blobs.add('e6e209fac5f0ed752b63ecc6ac831cb0e88ad7b34b0194a30093520e3653802e')
files={}
for h in sorted(blobs):
    p=WS/'blobs/sha256'/h[:2]/h
    assert sha(p)==h
    files['workspace/blobs/sha256/'+h[:2]+'/'+h]=p
excluded_prefixes=('bundle-','registration','readback','publication','final-sync','final-question','closing-')
for p in sorted(Q.rglob('*')):
    if not p.is_file() or '__pycache__' in p.parts or p.suffix in ['.pyc','.zip']:
        continue
    if p.name.startswith(excluded_prefixes):
        continue
    files['workspace/questions/'+Q.name+'/'+p.relative_to(Q).as_posix()]=p
manifest={'question':Q.name,'members':[{'name':name,'sha256':sha(p),'bytes':p.stat().st_size} for name,p in files.items()],
          'native_blobs':sorted(blobs),'environment':environment,'note':'Packaging-time snapshot; does not contain later registration/publication records or this manifest itself in the member list.'}
manifest['member_count']=len(files)
(OUT/'bundle-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
archive=OUT/'bundle-upstream-activity.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,p in files.items():
        info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,p.read_bytes())
    z.writestr('BUNDLE-MANIFEST.json',json.dumps(manifest,indent=2)+'\n')

replayed=[]
with tempfile.TemporaryDirectory(prefix='upstream-replay-',dir=os.environ['TMPDIR']) as directory:
    root=Path(directory)
    with zipfile.ZipFile(archive) as z:
        assert len(z.infolist())==len(files)+1
        for member in z.infolist():
            parts=Path(member.filename).parts
            assert not Path(member.filename).is_absolute() and '..' not in parts
            target=root/member.filename
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(z.read(member))
        for item in manifest['members']:
            assert sha(root/item['name'])==item['sha256']
    rq=root/'workspace/questions'/Q.name
    for script in ['analyze_upstream.py','analyze_followup.py','analyze_tead.py']:
        p=subprocess.run([sys.executable,str(rq/'scripts'/script)],capture_output=True,text=True,cwd=root)
        replayed.append({'script':script,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        assert p.returncode==0, p.stderr
    tables=['contrast-summary.tsv','sample-expression.tsv','all-gene-effects.tsv','followup-sample-expression.tsv','followup-all-gene-effects.tsv','tead-protein-source-values.tsv']
    exact=[]
    for name in tables:
        assert sha(rq/'outputs'/name)==sha(OUT/name), name
        exact.append({'file':name,'sha256':sha(OUT/name)})
    science=[]
    for name in ['executed-contrasts.json','followup-contrasts.json','tead-protein-contrasts.json']:
        a=json.loads((OUT/name).read_text())
        b=json.loads((rq/'outputs'/name).read_text())
        for d in [a,b]:
            if 'input_blobs' in d:
                d['input_blobs']=sorted(d['input_blobs'])
        assert a==b, name
        science.append(name)
result={'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'archive_entries':len(files)+1,
        'native_blob_count':len(blobs),'member_hashes_verified':True,'replayed':replayed,
        'byte_identical_tables':exact,'JSON_science_identical_ignoring_input_location_paths':science,
        'network_or_bio_needed_for_replay':False}
(OUT/'bundle-replay-verification.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='replayed'},indent=2))
