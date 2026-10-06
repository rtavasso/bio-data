"""Follow source links and narrower discovery queries; preserve exact responses."""
import concurrent.futures
import datetime
import hashlib
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_90f4fed27b7e4793'
out=q/'inputs/public'
jobs={}
for pmc in ['PMC4789348','PMC3628945','PMC8168556','PMC6497605']:
    jobs[pmc]=f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML'
queries={
 'matched-titleabs':'(TITLE_ABS:Nae1 OR TITLE_ABS:neddylation OR TITLE_ABS:MLN4924) AND (TITLE_ABS:NRF2 OR TITLE_ABS:NFE2L2) AND (TITLE_ABS:Schwann OR TITLE_ABS:PMP22)',
 'schwann-genetic-titleabs':'(TITLE_ABS:NRF2 OR TITLE_ABS:NFE2L2) AND (TITLE_ABS:Schwann OR TITLE_ABS:PMP22) AND (TITLE_ABS:knockout OR TITLE_ABS:knockdown OR TITLE_ABS:rescue)',
 'nae1-nrf2-titleabs':'TITLE_ABS:Nae1 AND (TITLE_ABS:NRF2 OR TITLE_ABS:NFE2L2)',
 'pmc8278275-identity':'EXT_ID:PMC8278275'
}
for key,query in queries.items():
    jobs['search-'+key]='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':query,'format':'json','resultType':'core','pageSize':100})
# Exact sample metadata from the series, not inferred library independence.
for acc in ['GSM7720312','GSM7720313','GSM7720314','GSM7720315','GSM7720316','GSM7720317','GSM7720318','GSM7720319','GSE113497','GSE113519']:
    jobs[acc]='https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?'+urllib.parse.urlencode({'acc':acc,'targ':'self','form':'text','view':'full'})

def get(item):
    key,url=item
    rec={'key':key,'url':url,'requested_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'bio-data-causal-audit/1.0'}),timeout=90) as r:
            data=r.read();rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
        suffix='.xml' if key.startswith('PMC') else '.json' if key.startswith('search-') else '.soft'
        path=out/(key+suffix);assert not path.exists(),path
        path.write_bytes(data);rec.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),path=str(path.relative_to(q)))
        if suffix=='.xml':
            root=ET.fromstring(data)
            (out/(key+'.txt')).write_text('\n'.join(' '.join(e.itertext()) for e in root.iter() if e.tag in {'article-title','abstract','title','p','caption'}))
        if suffix=='.json':rec['hitCount']=json.loads(data).get('hitCount')
    except Exception as e:rec['error']=str(e)
    (out/(key+'-receipt.json')).write_text(json.dumps(rec,indent=2,allow_nan=False))
    return rec
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:receipts=list(pool.map(get,jobs.items()))
(out/'retrieval-ledger-stage2.json').write_text(json.dumps(receipts,indent=2,allow_nan=False))
for r in receipts:print(r['key'],r.get('status'),r.get('bytes'),r.get('hitCount'),r.get('error',''))
