"""Targeted alternative transport and metadata inspection; no raw processing."""
import hashlib
import json
import pathlib
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from defusedxml import ElementTree as ET

Q = pathlib.Path(__file__).resolve().parents[1]
D = Q / 'inputs' / 'primary'
tasks = [(p + '-bioc-retry.xml', f'https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/{p}/unicode') for p in ['PMC5181599','PMC5800313']]
tasks += [(g + '-samples.soft', f'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={g}&targ=all&form=text&view=full') for g in ['GSE165206','GSE147285','GSE294160','GSE79115']]
queries = {'nrg-dose-search':'TITLE_ABS:(neuregulin AND Schwann AND dose AND myelination)', 'mechanics-search':'TITLE_ABS:(Schwann AND stiffness AND PMP22)', 'cis-nascent-search':'TITLE_ABS:(PMP22 AND (TEAD OR YAP OR neuregulin) AND (nascent OR CRISPR OR promoter))'}
for key, query in queries.items():
    tasks.append((key + '.json','https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urllib.parse.urlencode({'query':query,'format':'json','resultType':'core','pageSize':'30'})))
records = []
for name, url in tasks:
    path = D / name
    assert not path.exists(), path
    receipt = {'url':url, 'file':str(path.relative_to(Q)), 'started':datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'bio-data-research/1.0'}),timeout=90) as r:
            data = r.read()
            receipt.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
    except urllib.error.HTTPError as e:
        data=e.read()
        receipt.update(status=e.code,error=str(e))
    except Exception as e:
        data=b''
        receipt.update(status=None,error=repr(e))
    path.write_bytes(data)
    receipt.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    if 'bioc' in name and receipt.get('status')==200:
        try:
            root=ET.fromstring(data)
            passages=root.findall('.//passage')
            path.with_suffix('.txt').write_text('\n'.join(f'{i}: ' + ' '.join(p.findtext('text','').split()) for i,p in enumerate(passages))+'\n')
            receipt['passages']=len(passages)
        except Exception as e:
            receipt['parse_error']=repr(e)
    if name.endswith('search.json') and receipt.get('status')==200:
        d=json.loads(data)
        print(name, 'hitCount',d['hitCount'])
        for x in d['resultList']['result']:
            print(x.get('id'),x.get('pmcid'),x['title'])
    print(name, receipt.get('status'), len(data),receipt.get('passages',''))
    records.append(receipt)
    (D/'transport-r002.json').write_text(json.dumps(records,indent=2,allow_nan=False)+'\n')
