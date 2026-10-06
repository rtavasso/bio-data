"""Fetch primary texts, preserve failed HTTP attempts, parse without execution."""
import hashlib,json,textwrap
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from defusedxml import ElementTree as ET
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/primary'
R=[]
for p in ['PMC6128698','PMC13520134','PMC8780053','PMC11563883']:
    url=f'https://www.ebi.ac.uk/europepmc/webservices/rest/{p}/fullTextXML'
    name=p+'.xml';assert not (D/name).exists()
    r={'url':url,'started':datetime.now(timezone.utc).isoformat(),'name':name}
    try:
        with urlopen(Request(url,headers={'User-Agent':'bio-data-research/1.0'}),timeout=100) as f:
            data=f.read();r.update(status=f.status,headers=dict(f.headers),final_url=f.url)
    except HTTPError as e:data=e.read();r.update(status=e.code,error=str(e))
    except Exception as e:data=b'';r['error']=repr(e)
    (D/name).write_bytes(data);r.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    try:
        root=ET.fromstring(data);assert root.tag=='article',root.tag
        texts=[]
        for i,e in enumerate(root.iter()):
            if e.tag in ['title','article-title','p']:
                texts.append(f'{e.tag} element{i} id={e.get("id","")}\n'+textwrap.fill(' '.join(''.join(e.itertext()).split()),width=150))
        (D/(p+'.txt')).write_text('\n\n'.join(texts)+'\n')
    except Exception as e:r['parse_error']=repr(e)
    R.append(r);(D/'transport-paper-r001.json').write_text(json.dumps(R,indent=2)+'\n')
    print(name,r.get('status'),r['bytes'],r.get('parse_error'))
