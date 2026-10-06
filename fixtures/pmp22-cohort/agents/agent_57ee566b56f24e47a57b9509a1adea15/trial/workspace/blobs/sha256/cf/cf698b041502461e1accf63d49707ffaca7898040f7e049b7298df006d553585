"""Create esummary queries from exact returned GDS IDs; no guessed accessions."""
import json,os,urllib.parse
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
x=json.loads((q/'inputs/public/geo-injury-search.json').read_text())['esearchresult'];ids=x['idlist']
assert int(x['count'])==len(ids), 'paginate esearch before claiming exhaustive returned query'
urls={}
for start in range(0,len(ids),40):
    urls[f'geo-injury-summaries-{start}.json']='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?'+urllib.parse.urlencode({'db':'gds','id':','.join(ids[start:start+40]),'retmode':'json'})
(q/'inputs/geo-summaries-urls.json').write_text(json.dumps(urls,indent=2));print('SOURCE_IDS',len(ids),'batches',len(urls))
