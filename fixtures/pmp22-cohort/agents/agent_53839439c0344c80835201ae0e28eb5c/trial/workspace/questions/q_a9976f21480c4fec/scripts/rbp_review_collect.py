"""Select existing shared evidence and query results for a bounded peer review; no raw processing."""
import json
import csv
from collections import Counter
from pathlib import Path

q=Path(__file__).resolve().parents[1]
o=q/'inputs/rbp-review'
o.mkdir(exist_ok=True)
p=Path('.hermes/cache/terminal-output/out-1791236495-8908-10f0.log')
records=[json.loads(line) for line in p.read_text().splitlines() if line.startswith('{')]
for r in records:
    if r.get('id','').startswith('artifact_'):
        (o/(r['id']+'.json')).write_text(json.dumps(r,indent=2))
        print('ARTIFACT',r['id'],'top_keys',list(r),'manifest_except_derivation',
              {k:v for k,v in r['manifest'].items() if k!='derivation'})
    elif 'query' in r:
        (o/('forum-'+r['query']+'.json')).write_text(json.dumps(r,indent=2))
        print('FORUM',r['query'],'total',r.get('total'),'next_offset',r.get('next_offset'))
        for item in r['items']:
            if r['query']=='eCLIP' or any(x in item['summary'] for x in ['PUM2','PUM1','123016','159510','13234107']):
                print(item['subject'],item['title'],item['summary'])

table=json.loads((o/'artifact_6a0119b8ecd1d29ff44d122e74920f2097d6b1c9179ab9572f2237585effc047.json').read_text())
with Path(table['path']).open() as f:
    rows=list(csv.DictReader(f,delimiter='\t'))
print('JOINT_STATUS',dict(Counter(r['primary_joint_candidate'] for r in rows)))
print('NON_FALSE_ROWS',[(r['rbp'],r['cell'],r['rna_experiment'],r['rna_status'],r['primary_joint_candidate']) for r in rows if r['primary_joint_candidate']!='False'])
