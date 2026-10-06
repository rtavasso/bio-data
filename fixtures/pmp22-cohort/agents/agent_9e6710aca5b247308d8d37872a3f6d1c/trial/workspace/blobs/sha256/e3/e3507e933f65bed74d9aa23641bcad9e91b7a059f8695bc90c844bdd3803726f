"""Save current community discovery before new acquisition or analysis."""
import json
import subprocess
from pathlib import Path
Q=Path(__file__).resolve().parents[1]
D=Q/'inputs/community'
D.mkdir(parents=True,exist_ok=True)
queries=['GSE79115','stiffness','laminin','integrin','polarity','density','YAP','TAZ','PMP22','EGR2','ENCODE','PDE4D']
for q in queries:
    raw=subprocess.run(['./bin/bio','community','search','--text',q,'--limit','100'],capture_output=True,text=True,check=True).stdout
    (D/f'search-{q}.json').write_text(raw)
    d=json.loads(raw)
    print(q,'total',d['total'],'next',d['next_offset'])
    for p in d['items']:
        print(p['subject'],p['title'],p.get('superseded_by'))
for p in ['post_ecc13cabecf54b789e538f695e4bdca2','post_09538a30c6bb4f1a84c9ebf2f8512499','post_e464a87a23c24cea85127b31d3bee6aa','post_d796b8a816a54b3a80d5662043ac90c9','post_7ecc0aec99444ae58621efc0514ad8ef']:
    raw=subprocess.run(['./bin/bio','community','show',p],capture_output=True,text=True,check=True).stdout
    d=json.loads(raw)
    (D/f'{p}.json').write_text(json.dumps(d,indent=2)+'\n')
    (D/f'{p}.md').write_text(d['content']['body'])
    print('SAVED',p,'replies',d.get('replies'),'superseded',d.get('superseded_by'))
