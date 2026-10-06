"""Integrity checks for scientific handoff; no new statistical claims."""
from pathlib import Path
import json,hashlib,math
import pandas as pd,numpy as np
q=Path(__file__).resolve().parents[1];o=q/'outputs';reg=json.loads((o/'continuation-registration.json').read_text());checks=[]
for name,r in reg['outputs'].items():
 p=o/name;actual=hashlib.sha256(p.read_bytes()).hexdigest();assert actual==r['output_blob'],(name,actual,r['output_blob']);assert not r['conflicting_outputs'] and not r['warning'],name
 checks.append({'output':name,'sha256':actual,'artifact':r['artifact'],'matches_registered_blob':True})
 if p.suffix=='.tsv':
  df=pd.read_csv(p,sep='\t');n=df.select_dtypes(include=[np.number]);assert not np.isinf(n.to_numpy()).any(),name
m=json.loads((o/'mechanisms.json').read_text());nodes={n['id'] for n in m['nodes']};edges={e['id'] for e in m['edges']};assert len(nodes)==len(m['nodes']) and len(edges)==len(m['edges'])
for e in m['edges']:
 assert e['source'] in nodes and e['target'] in nodes
 assert e['status'] in ['supported','contested','hypothesis']
 if e['status']!='hypothesis':assert e['evidence']
for f in m['frontier']:assert f['node'] in nodes
v=json.loads((o/'investigations.json').read_text());ids={x['id'] for x in v['items']};assert len(ids)==len(v['items']);known={r['artifact'] for r in reg['outputs'].values()};required=['id','priority','question','alternatives','readout','assets','prerequisites','status','artifacts','finding','limitation','next_action','blocker_evidence']
for x in v['items']:
 assert all(k in x for k in required),x['id']
 if x['status']=='analyzed':assert x['artifacts'] and all(a in known for a in x['artifacts']) and x['finding'],x['id']
 if x['status']=='blocked':
  assert x['limitation'] and x['blocker_evidence'],x['id']
  for p in x['blocker_evidence']:assert (q/p).exists(),p
 if x['status']=='deferred':assert x['limitation'] and x['next_action']
assert v['status']=='in_progress'
# Saved current maps equal newest numbered snapshots; all earlier snapshots remain present.
for stem,current in [('mechanisms',m),('investigations',v)]:
 assert (o/(stem+'.json')).read_bytes()==(o/f'{stem}.r{current["revision"]:03d}.json').read_bytes()
assert all((o/f'mechanisms.r{r:03d}.json').exists() for r in range(2,9))
assert (o/'mechanisms.initial.json').exists() and (o/'REPORT.inherited.md').exists()
budget=json.loads((o/'continuation-budget.json').read_text());assert budget['requests_total']<=150 and budget['new_bytes_accounted']<1073741824
summary={'checked_registered_outputs':len(checks),'output_integrity':checks,'mechanism_revision':m['revision'],'nodes':len(nodes),'edges':len(edges),'investigation_revision':v['revision'],'items':len(v['items']),'status_counts':{s:sum(x['status']==s for x in v['items']) for s in sorted({x['status'] for x in v['items']})},'high_priority_all_analyzed_or_source_blocked':all(x['status'] in ['analyzed','blocked'] for x in v['items'] if x['priority']=='high'),'remaining_scope':'Open biological system; narrower analyzed items need not resolve their alternatives. Hormonal coverage remains deferred.','budget':budget}
(o/'continuation-validation.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps({k:val for k,val in summary.items() if k not in ['output_integrity','budget']},indent=2))
