"""Freeze exact native measurements and metadata for a reproducible processed-data screen."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]
w=Path(os.environ['BIO_WORKSPACE'])
selection=json.loads((q/'inputs/selection-r001.json').read_text())
labels=['gencode19-encode-gtf-r001','encore-paper-xml-r001','encore-correction-xml-r001','encore-supplement-zip-r001','merge-peaks-readme-r001','idr-file-meta-r001']
labels += ['file-'+r['file']['File accession']+'-r001' for r in selection if r['role'] in ['idr_peaks','de_paired']]
entries=[]
for label in labels:
    p=q/'inputs/http'/(label+'.payload')
    rec=json.loads((q/'inputs/http'/(label+'.receipt.json')).read_text())
    assert rec['complete'] and rec['status']==200
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha==rec['sha256']
    blob=w/'blobs/sha256'/sha[:2]/sha
    if not blob.exists():
        subprocess.run(['./bin/bio','object','add',str(p)],capture_output=True,text=True,check=True)
    assert blob.exists() and blob.stat().st_size==p.stat().st_size
    entries.append({'name':label,'sha256':sha,'bytes':p.stat().st_size,'source_url':rec['url']})
for name in ['selection-r001.json','publication-file-metadata.json','source-assay-pairs.json']:
    p=q/'inputs'/name
    subprocess.run(['./bin/bio','object','add',str(p)],capture_output=True,text=True,check=True)
    entries.append({'name':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
manifest={'version':1,'question':q.name,'selection':'selection-r001.json','files':entries,'endpoints':['PMP22 binding association','PMP22 steady-state RNA response'],'not_estimated':['RNA decay','promoter initiation','Schwann transfer']}
p=q/'inputs/screen-manifest-r001.json'
assert not p.exists()
p.write_text(json.dumps(manifest,indent=2,allow_nan=False))
print('FROZEN',len(entries),'INPUTS',sum(e['bytes'] for e in entries),'BYTES')
