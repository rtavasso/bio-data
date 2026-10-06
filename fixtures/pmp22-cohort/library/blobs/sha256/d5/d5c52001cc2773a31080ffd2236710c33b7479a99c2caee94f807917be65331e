"""Compile human-curated subedges with executed values; audit source-text coverage."""
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

Q = Path(__file__).resolve().parents[1]
OUT = Q/'outputs'
edges = json.loads((Q/'inputs/curated-edges.json').read_text())
effects = pd.read_csv(OUT/'executed-contrasts.tsv',sep='\t')
primary = effects.loc[effects.variant.eq('primary')&effects.pseudocount.eq(.5)]
for edge in edges:
    edge['interpretation_author']='agent_9e6710aca5b247308d8d37872a3f6d1c'
    if 'contrast' in edge:
        row = primary.loc[primary.contrast.eq(edge['contrast'])&primary.endpoint.eq(edge['endpoint'])]
        assert len(row)==1
        for key in ['effect_log2','ci95_low','ci95_high','baseline_eligible','statuses_valid']:
            value = row.iloc[0][key]
            edge[key] = value.item() if hasattr(value,'item') else value
pd.DataFrame(edges).to_csv(OUT/'intervention-pathway-PMP22-edges.tsv',sep='\t',index=False)
(OUT/'hypothesis-map.json').write_text(json.dumps({'edges':edges,'scope':'question-local authored interpretation; quantitative values joined from executed data; not a platform prior graph'},indent=2,allow_nan=False)+'\n')
paths=[Q/'inputs/primary/PMC6128698-retry.txt',Q/'inputs/primary/PMC13520134-retry.txt',Q/'inputs/primary/PMC5414202.xml.txt',Q/'inputs/primary/PMC8780053.txt',Q.parent/'q_e835197734394f30/inputs/primary/PMC4925303.txt']
audit=[]
for path in paths:
    data=path.read_bytes()
    lines=data.decode().splitlines()
    hits=[{'line':i+1,'text':line} for i,line in enumerate(lines) if re.search(r'\bPMP22\b',line,re.I)]
    audit.append({'file':str(path),'sha256':hashlib.sha256(data).hexdigest(),'literal_PMP22_hits':hits,'scope':'whole saved main article text including references, not exhaustive supplement audit'})
novelty={'status':'candidate incidental quantitative observations, not established new mechanism','known':'YAP/TAZ loss and broad myelin/Pmp22 decrease already reported in PMC4925303 and PMC5414202. ECM-RAP2-Hippo and compression-cPLA2/AP1 mechanisms already source findings. This fork claims only executed target-specific contrasts, relative-regulator effect comparison, and failed cross-mechanics prediction.','potential_addition':'PMP22 stiffness sign/interaction in HEK and contrary compression RNA point response may be overlooked incidentals; main-text literal search is insufficient to prove global novelty.','sources':audit,'limits':['Not an exhaustive systematic literature search','No matched nascent initiation or direct activity assay','Independent studies corroborate quantitative genetics; processing workbook corroborates compression calculation but not biology']}
(OUT/'novelty-audit.json').write_text(json.dumps(novelty,indent=2,allow_nan=False)+'\n')
print('Edges',len(edges),'novelty text hits',[(x['file'].split('/')[-1],len(x['literal_PMP22_hits'])) for x in audit])
