"""Acquire source-listed metadata documents and selected static supplements only."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.parse import urljoin
from retrieve import retrieve
q=Path(__file__).resolve().parents[1]
base='https://www.encodeproject.org'

def get(label,url):
    receipt=q/'inputs/http'/(label+'.receipt.json')
    if receipt.exists():
        return json.loads(receipt.read_text())
    return retrieve(label,url)

def document(ref):
    key=ref.strip('/').split('/')[-1]
    r=get('doc-'+key+'-meta-r001',base+ref+'?format=json')
    if r.get('status')!=200 or not r['complete']:
        return
    obj=json.loads((q/'inputs/http'/('doc-'+key+'-meta-r001.payload')).read_text())
    attachment=obj.get('attachment',{})
    href=attachment.get('href')
    if href:
        get('doc-'+key+'-attachment-r001',urljoin(base+ref,href))
refs=set()
for c in ['eclip','hepg2','k562','secondary','batch']:
    obj=json.loads((q/'inputs/http'/f'encode-{c}-meta-r001.payload').read_text())
    refs.update(obj['documents'])
with ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(document,sorted(refs)))
# Native supplement names are taken from the downloaded article XML.
for i in [4,6,7,10,11,12,13]:
    get(f'supp-{i}-r001',f'https://static-content.springer-cdn.com/esm/art%3A10.1038%2Fs41586-020-2077-3/MediaObjects/41586_2020_2077_MOESM{i}_ESM.xlsx')
get('encore-correction-xml-r001','https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7962576/fullTextXML')
