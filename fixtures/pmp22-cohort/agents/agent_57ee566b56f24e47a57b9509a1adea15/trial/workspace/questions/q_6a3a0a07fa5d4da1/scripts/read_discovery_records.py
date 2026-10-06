"""Read-only compact discovery inspection via public CLI; no matrix outcomes."""
import concurrent.futures,json,os,subprocess
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
paths=[p for p in (q/'outputs').glob('discovery-*.json') if '.pretty.' not in p.name and 'resources' not in p.name]
ids=set()
for p in paths:
    obj=json.loads(p.read_text())
    if isinstance(obj,dict):
        ids.update(obj.get('resources',[]))
(q/'inputs/discovery-records').mkdir(exist_ok=True,parents=True)
def one(id):
    p=q/'inputs/discovery-records'/f'{id}.json'
    if not p.exists():
        r=subprocess.run(['./bin/bio','data','show',id],capture_output=True,text=True,check=True); p.write_text(r.stdout)
    x=json.loads(p.read_text())
    facts=[y['facts']['source_record'] for y in x['profiles'] if y.get('facts',{}).get('source_record')]
    a=facts[0]
    return {'subject':id,'pmid':a.get('pmid'),'pmcid':a.get('pmcid'),'title':a.get('title'),'abstract':a.get('abstractText'),'year':a.get('pubYear')}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    rows=list(pool.map(one,sorted(ids)))
(q/'outputs/discovery-titles.json').write_text(json.dumps(rows,indent=2))
for r in rows: print(r['pmid'],r['pmcid'],r['title'])
print('UNIQUE_RECORDS',len(rows))
