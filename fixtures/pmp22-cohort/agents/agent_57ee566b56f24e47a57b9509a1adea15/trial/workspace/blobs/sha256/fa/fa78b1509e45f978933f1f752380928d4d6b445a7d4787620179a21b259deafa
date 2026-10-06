"""Read public GEO query results as a bounded experiment inventory."""
import json,os,re
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
rows=[]
for p in sorted((q/'inputs/public').glob('geo-injury-summaries-*.json')):
    if '.receipt.' in p.name:continue
    x=json.loads(p.read_text())['result']
    for id in x['uids']:
        a=x[id];rows.append(a)
(q/'outputs/geo-injury-inventory.json').write_text(json.dumps(rows,indent=2))
for a in rows:
    print(a.get('accession'),a.get('n_samples'),a.get('title'))
    if not re.search(r'dorsal root|DRG|sensory neuron|retina|ganglion|spinal cord|muscle',a.get('title',''),re.I):print(' ',a.get('summary','')[:1200])
print('RETURNED_SERIES',len(rows))
