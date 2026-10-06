"""Retrieve bounded primary texts/metadata with actual transport receipts."""
import concurrent.futures
import datetime
import hashlib
import json
import pathlib
import urllib.error

import urllib.request
import xml.etree.ElementTree as ET

Q = pathlib.Path(__file__).resolve().parents[1]
D = Q / 'inputs' / 'primary'
D.mkdir(parents=True, exist_ok=True)
PMCS = ['PMC5181599', 'PMC4925303', 'PMC8124465', 'PMC5800313', 'PMC11592338', 'PMC10959528', 'PMC5287714']
TASKS = [(p + '.xml', f'https://www.ebi.ac.uk/europepmc/webservices/rest/{p}/fullTextXML') for p in PMCS]

TASKS += [(g + '.soft', f'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={g}&targ=self&form=text&view=full') for g in ['GSE147285','GSE294160','GSE201623']]

def fetch(task):
    name, url = task
    path = D / name
    receipt = {'url':url, 'file':str(path.relative_to(Q)), 'started':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if path.exists():
        raise RuntimeError(f'Refusing overwrite: {path}')
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'bio-data-research/1.0'})
        with urllib.request.urlopen(req, timeout=75) as r:
            data = r.read()
            receipt.update(status=r.status, final_url=r.url, content_type=r.headers.get('Content-Type'))
    except urllib.error.HTTPError as e:
        data = e.read()
        receipt.update(status=e.code, error=str(e))
    except Exception as e:
        data = b''
        receipt.update(status=None, error=repr(e))
    path.write_bytes(data)
    receipt.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    if name.endswith('.xml') and receipt.get('status') == 200:
        try:
            root = ET.fromstring(data)
            assert root.tag == 'article', root.tag
            lines = []
            for element in root.iter():
                if element.tag in ('article-title', 'title', 'p', 'table', 'caption'):
                    text = ' '.join(''.join(element.itertext()).split())
                    if text:
                        lines.append(f"{element.tag} {element.get('id','')} | {text}")
            path.with_suffix('.txt').write_text('\n'.join(lines) + '\n')
            receipt['valid_article_xml'] = True
        except Exception as e:
            receipt.update(valid_article_xml=False, parse_error=repr(e))
    return receipt

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    records = list(pool.map(fetch, TASKS))
(D / 'transport-r001.json').write_text(json.dumps(records, indent=2, allow_nan=False) + '\n')
for r in records:
    print(r['file'], r.get('status'), r['bytes'], r.get('valid_article_xml'), r.get('error',''))
