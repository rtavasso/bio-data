"""Compile actual failed/HTML retrieval receipts without inventing absent requests."""
import hashlib,json,os
from pathlib import Path
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';items=[]
for directory in [Q/'inputs/public',Q/'inputs/primary']:
    for p in directory.glob('*.receipt.json'):
        r=json.loads(p.read_text());native=Path(str(p)[:-len('.receipt.json')])
        # Older primary transporter uses PMCxyz.receipt.json with PMCxyz.xml bytes.
        if not native.exists() and (directory/(native.name+'.xml')).exists():native=directory/(native.name+'.xml')
        if native.exists() and r.get('sha256'):assert hashlib.sha256(native.read_bytes()).hexdigest()==r['sha256']
        prefix=native.read_bytes()[:300].lower() if native.exists() else b''
        html=native.suffix in ['.xml','.json','.gz'] and (b'<html' in prefix or b'<!doctype html' in prefix)
        if r.get('error') or r.get('status',0)>=400 or html:
            items.append({'receipt':str(p.relative_to(Q)),'status':r.get('status'),'bytes':r.get('bytes'),'sha256':r.get('sha256'),'error':r.get('error'),'unexpected_html':html,'requested_url':r.get('requested_url'),'interpretation':'This attempted route failed or yielded non-scientific HTML; not a claim that the dataset/feature does not exist.'})
result={'actual_receipt_count':len(items),'scope':'Native files and receipts in this question only; successful alternatives and exclusions described in LABBOOK. Wrong-identifier attempts remain excluded from scientific evidence.','failures':items}
(Q/'outputs/retrieval-failure-inventory.json').write_text(json.dumps(result,indent=2));print('VERIFIED_FAILED_OR_HTML_RECEIPTS',len(items))
