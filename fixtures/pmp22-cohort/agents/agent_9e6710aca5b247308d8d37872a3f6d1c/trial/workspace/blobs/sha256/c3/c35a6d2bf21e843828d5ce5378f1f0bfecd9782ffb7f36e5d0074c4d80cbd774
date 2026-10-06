"""Retrieve exact source metadata and primary text; retain attempt receipts."""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from datetime import datetime,timezone
import hashlib,json,shutil,textwrap
from defusedxml import ElementTree as ET
Q=Path(__file__).resolve().parents[1]
D=Q/'inputs/primary';D.mkdir(parents=True,exist_ok=True)
items={
'GSE292211-family.soft':'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE292211&targ=all&form=text&view=full',
'GSE94990-family.soft':'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE94990&targ=all&form=text&view=full',
'GSE98547-family.soft':'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE98547&targ=all&form=text&view=full',
'PMC5414202.xml':'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC5414202/fullTextXML',
'GSE98547-series.soft':'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE98547&targ=self&form=text&view=full',
}
receipts=[]
for name,url in items.items():
    assert not (D/name).exists()
    assert shutil.disk_usage(D).free>10*1024**3
    r={'url':url,'started':datetime.now(timezone.utc).isoformat(),'path':name}
    try:
        with urlopen(Request(url,headers={'User-Agent':'bio-data-research/1.0'}),timeout=100) as f:
            data=f.read();r.update(status=f.status,final_url=f.url,headers=dict(f.headers))
    except HTTPError as e:
        data=e.read();r.update(status=e.code,error=str(e))
    except Exception as e:
        data=b'';r.update(error=repr(e))
    (D/name).write_bytes(data)
    r.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),finished=datetime.now(timezone.utc).isoformat())
    if name.endswith('.xml'):
        try:
            root=ET.fromstring(data)
            text=[]
            for i,e in enumerate(root.iter()):
                if e.tag in ('p','title'):
                    text.append(f'{e.tag} element{i} id={e.get("id","")}\n'+textwrap.fill(' '.join(''.join(e.itertext()).split()),width=150))
            (D/(name+'.txt')).write_text('\n\n'.join(text))
        except Exception as e:
            r['parse_error']=repr(e)
    receipts.append(r)
    (D/'transport-meta-r001.json').write_text(json.dumps(receipts,indent=2)+'\n')
    print(name,r.get('status'),r['bytes'],r.get('error'),r.get('parse_error'))
    if '.soft' in name:
        meta=[];active=False
        for l in data.decode(errors='replace').splitlines():
            if l.startswith('^SERIES') or l.startswith('^SAMPLE'): active=True
            if l.startswith('^PLATFORM'):active=False
            if active and l.startswith(('^','!Series_title','!Series_pubmed','!Series_overall','!Series_supplementary','!Sample_title','!Sample_source','!Sample_characteristics','!Sample_data_processing','!Sample_treatment','!Sample_growth','!Sample_supplementary')):
                meta.append(l)
        (D/(name+'.metadata.txt')).write_text('\n'.join(meta)+'\n')
