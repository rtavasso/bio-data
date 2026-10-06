from pathlib import Path
from urllib.parse import urlencode
import json
from upstream_acquire import acquire
Q=Path(__file__).resolve().parents[1];I=Q/'inputs/upstream';O=Q/'outputs/upstream'
queries=[('novelty-nae1-abstract','TITLE_ABS:((Nae1 OR neddylation) AND (Schwann OR myelination) AND (Nrf2 OR Nqo1 OR Slc7a11 OR antioxidant))'),('novelty-pmp22-abstract','TITLE_ABS:((PMP22 OR "peripheral myelin protein 22") AND (NRF2 OR NFE2L2 OR neddylation OR Nae1))')]
for name,q in queries: print(json.dumps(acquire(dict(name=name+'.json',url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode(dict(query=q,format='json',pageSize=100))))))
print(json.dumps(acquire(dict(name='PRJEB20661-library.tsv',url='https://www.ebi.ac.uk/ena/portal/api/filereport?'+urlencode(dict(accession='PRJEB20661',result='read_run',fields='run_accession,experiment_accession,sample_alias,library_name,fastq_ftp',format='tsv'))))))
rows=[]
for p in I.glob('novelty-*.json'):
 d=json.loads(p.read_text()); r=d.get('resultList',{}).get('result',[]);rows.append(dict(file=p.name,query=d.get('request'),hits=d.get('hitCount'),returned=len(r),truncated=bool(d.get('nextCursorMark')),results=[{k:a.get(k) for k in ['id','pmcid','title','doi','pubYear','pubType']} for a in r]))
(O/'novelty-search-summary.json').write_text(json.dumps(rows,indent=2));
for a in rows:
 print(a['file'],a['hits'],a['returned']);
 for r in a['results']:
  if any(t in (r.get('title') or '').lower() for t in ['schwann','myelin','neddyl','nrf2','oxidative','trembler']):print(r)
