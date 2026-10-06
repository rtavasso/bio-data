"""Bounded read-only primary-source/metadata retrieval; never execute source content."""
import concurrent.futures
import datetime
import hashlib
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

q = Path(os.environ['BIO_WORKSPACE']) / 'questions/q_90f4fed27b7e4793'
out = q / 'inputs/public'
out.mkdir(parents=True, exist_ok=True)
jobs = {}
for pmc in ['PMC11014456', 'PMC5658359', 'PMC8278275', 'PMC12596376', 'PMC5802790']:
    jobs[pmc] = f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML'
queries = {
    'nae1-nrf2-schwann': '(Nae1 OR neddylation OR MLN4924) AND (NRF2 OR NFE2L2) AND (Schwann OR PMP22)',
    'schwann-nrf2-genetic': '(NRF2 OR NFE2L2) AND (Schwann OR PMP22) AND (knockout OR knockdown OR rescue)',
    'neddylation-nrf2-genetic': '(neddylation OR MLN4924) AND (NRF2 OR NFE2L2) AND (knockdown OR knockout)',
    'lxr-title': 'TITLE:"Liver X Receptor exerts a protective effect against the oxidative stress in the peripheral nerve"'
}
for key, query in queries.items():
    jobs['search-' + key] = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urllib.parse.urlencode({'query': query, 'format':'json','resultType':'core','pageSize':100})
for acc in ['GSE241269', 'GSE113522']:
    jobs[acc] = 'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?' + urllib.parse.urlencode({'acc':acc,'targ':'self','form':'text','view':'full'})

def get(item):
    key, url = item
    receipt = {'key':key, 'url':url, 'requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'bio-data-research-evidence-audit/1.0'}), timeout=90) as r:
            data = r.read()
            receipt.update(status=r.status, final_url=r.url, content_type=r.headers.get('Content-Type'))
        suffix = '.json' if key.startswith('search-') else '.xml' if key.startswith('PMC') else '.soft'
        path = out / (key+suffix)
        path.write_bytes(data)
        receipt.update(path=str(path.relative_to(q)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        if suffix == '.xml':
            root = ET.fromstring(data)
            # Read-only text rendition. Original XML bytes are retained.
            text = '\n'.join(' '.join(e.itertext()) for e in root.iter() if e.tag in {'article-title','abstract','title','p','caption','table-wrap-foot'})
            (out / (key+'.txt')).write_text(text)
        elif suffix == '.json':
            d = json.loads(data)
            receipt['hitCount'] = d.get('hitCount')
    except Exception as e:
        receipt['error'] = str(e)
    (out / (key+'-receipt.json')).write_text(json.dumps(receipt, indent=2, allow_nan=False))
    return receipt

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    receipts = list(pool.map(get, jobs.items()))
(out / 'retrieval-ledger.json').write_text(json.dumps(receipts, indent=2, allow_nan=False))
for r in receipts:
    print(r['key'], r.get('status'), r.get('bytes'), r.get('hitCount'), r.get('error',''))
