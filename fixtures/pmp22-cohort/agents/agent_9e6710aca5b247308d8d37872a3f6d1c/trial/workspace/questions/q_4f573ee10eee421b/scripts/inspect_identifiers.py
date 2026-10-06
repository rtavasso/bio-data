"""Inspect nonunique native tracking IDs without collapsing source rows."""
import json
from pathlib import Path
import pandas as pd
Q=Path(__file__).resolve().parents[1];W=Q.parents[1]
M=json.loads((Q/'inputs/acquisition/manifest.json').read_text())
rows=[]
for s in ['GSE94990','GSE98547']:
    for item in [x for x in M if x['series']==s]:
        df=pd.read_csv(W/item['path'],compression='gzip',sep='\t',dtype=str,keep_default_na=False)
        d=df.loc[df.tracking_id.duplicated(keep=False)]
        comp=df['tracking_id']+'|'+df['locus']
        x={'file':item['name'],'rows':len(df),'duplicate_id_rows':len(d),'duplicate_composite_rows':int(comp.duplicated(keep=False).sum()),'duplicate_examples':d.iloc[:15].to_dict('records'),'panel_PMP22':df.loc[df.gene_short_name.str.upper().eq('PMP22')].to_dict('records')}
        rows.append(x)
        print(item['name'],'rows',len(df),'duplicate_ids',len(d),'duplicate_id_locus',x['duplicate_composite_rows'],'PMP22',x['panel_PMP22'])
        if len(d): print(d.iloc[:8].to_string(index=False))
(Q/'outputs/native-identifier-diagnostic.json').write_text(json.dumps(rows,indent=2)+'\n')
