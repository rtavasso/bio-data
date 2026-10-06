"""Bounded primary literature discovery with original request/response receipts."""
import json,hashlib
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/discovery';D.mkdir(parents=True,exist_ok=True)
queries={
'compression':'(HEI-286 OR Stupakov) AND (compression OR mechanical)',
'rap2':'EXT_ID:30135582 AND SRC:MED',
'primary-mechanics':'Schwann AND (stiffness OR geometry OR laminin OR integrin OR polarity) AND (RNA-seq OR transcriptome OR microarray)',
'novelty':'PMP22 AND (stiffness OR compression OR RAP2 OR YAP OR TAZ)',
}
for key,q in queries.items():
    url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode({'query':q,'format':'json','resultType':'core','pageSize':100})
    r={'url':url,'query':q,'started':datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url,headers={'User-Agent':'bio-data-research/1.0'}),timeout=90) as f:
            data=f.read();r.update(status=f.status,headers=dict(f.headers),url_final=f.url)
        d=json.loads(data)
        (D/(key+'.json')).write_bytes(data)
        r.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),total=d.get('hitCount'),returned=len(d.get('resultList',{}).get('result',[])))
        print(key,'hits',d.get('hitCount'))
        for x in d.get('resultList',{}).get('result',[]):print(x.get('id'),x.get('pmcid'),x.get('title'))
    except Exception as e: r['error']=repr(e);print(key,r)
    (D/(key+'.receipt.json')).write_text(json.dumps(r,indent=2)+'\n')
