"""One documented alternative primary text retrieval, keeping prior failed bytes."""
import hashlib,json,textwrap
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from defusedxml import ElementTree as ET
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/primary'
p='PMC11563883';url=f'https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/{p}/unicode'
r={'url':url,'started':datetime.now(timezone.utc).isoformat()}
try:
    with urlopen(Request(url,headers={'User-Agent':'bio-data-research/1.0'}),timeout=100) as f:
        data=f.read();r.update(status=f.status,headers=dict(f.headers),final_url=f.url)
except HTTPError as e:data=e.read();r.update(status=e.code,error=str(e))
except Exception as e:data=b'';r['error']=repr(e)
assert not(D/(p+'-bioc.xml')).exists();(D/(p+'-bioc.xml')).write_bytes(data)
r.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
try:
    root=ET.fromstring(data)
    texts=[textwrap.fill(''.join(x.itertext()),width=150) for x in root.iter('text')]
    assert texts
    (D/(p+'-bioc.txt')).write_text('\n\n'.join(texts)+'\n');r['text_passages']=len(texts)
except Exception as e:r['parse_error']=repr(e)
(D/'transport-paper-r003.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
