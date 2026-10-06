"""Retrieve directly identified remaining primary texts with durable receipts."""
import hashlib
import json
import pathlib
import urllib.request
import urllib.error
from datetime import datetime,timezone
from defusedxml import ElementTree as ET
Q=pathlib.Path(__file__).resolve().parents[1]
D=Q/'inputs'/'primary'
tasks=[('PMC5181599.html','https://pmc.ncbi.nlm.nih.gov/articles/PMC5181599/'),('PMC2199210.xml','https://www.ebi.ac.uk/europepmc/webservices/rest/PMC2199210/fullTextXML')]
receipts=[]
for name,url in tasks:
    path=D/name
    assert not path.exists()
    row={'url':url,'file':str(path.relative_to(Q)),'started':datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'bio-data-research/1.0'}),timeout=90) as r:
            data=r.read()
            row.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
    except urllib.error.HTTPError as e:
        data=e.read()
        row.update(status=e.code,error=str(e))
    except Exception as e:
        data=b''
        row.update(status=None,error=repr(e))
    path.write_bytes(data)
    row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    if name.endswith('.xml') and row.get('status')==200:
        try:
            root=ET.fromstring(data)
            assert root.tag=='article'
            path.with_suffix('.txt').write_text('\n'.join(e.tag+' '+e.get('id','')+' | '+' '.join(''.join(e.itertext()).split()) for e in root.iter() if e.tag in ('article-title','p','title','caption'))+'\n')
            row['valid_article_xml']=True
        except Exception as e:
            row['parse_error']=repr(e)
    receipts.append(row)
    (D/'transport-r003.json').write_text(json.dumps(receipts,indent=2,allow_nan=False)+'\n')
    print(name,row.get('status'),len(data))
