"""Fetch selected immutable processed measurements, never raw reads or downloaded code."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from retrieve import retrieve
q=Path(__file__).resolve().parents[1]
a=argparse.ArgumentParser()
a.add_argument('mode',choices=['probe','primary','batch'])
args=a.parse_args()
rows=json.loads((q/'inputs/selection-r001.json').read_text())
if args.mode=='probe':
    sel=[]
    for cell in ['HepG2','K562']:
        for role in ['idr_peaks','de_paired','de_batch']:
            sel.append(next(r for r in rows if r['cell']==cell and r['role']==role))
elif args.mode=='primary':
    sel=[r for r in rows if r['role'] in ['idr_peaks','de_paired']]
else:
    sel=[r for r in rows if r['role']=='de_batch']

def fetch(row):
    f=row['file']
    label='file-'+f['File accession']+'-r001'
    receipt=q/'inputs/http'/(label+'.receipt.json')
    if receipt.exists():
        rec=json.loads(receipt.read_text())
    else:
        rec=retrieve(label,f['S3 URL'] or 'https://www.encodeproject.org'+f['File download URL'])
    if rec.get('status')!=200 or not rec.get('complete'):
        return {'file':f['File accession'],'status':'retrieval_failure'}
    p=q/'inputs/http'/(label+'.payload')
    assert p.stat().st_size==int(f['Size']), f['File accession']
    assert hashlib.md5(p.read_bytes()).hexdigest()==f['md5sum'], f['File accession']
    return {'file':f['File accession'],'status':'verified','bytes':p.stat().st_size,'md5':f['md5sum'],'sha256':rec['sha256']}
with ThreadPoolExecutor(max_workers=4) as pool:
    outcomes=list(pool.map(fetch,sel))
(q/'inputs'/('download-validation-'+args.mode+'.json')).write_text(json.dumps(outcomes,indent=2))
print('VERIFIED',sum(x['status']=='verified' for x in outcomes),'OF',len(outcomes))
