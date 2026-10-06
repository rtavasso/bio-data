"""Metadata-only assessment of putative independent repair validation design."""
import json,os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
x=json.loads((q/'outputs/design-GSE216665.json').read_text())
seen={}
for p in x['profiles']:
    f=p.get('facts',{})
    if f.get('source_record'): print('SOURCE',f['source_record'])
    for a in f.get('related_source_context',[]):
        d=a.get('body',{}).get('fields',{})
        if d: seen[(d.get('Sample_geo_accession') or d.get('Series_geo_accession') or [a.get('native_id','')])[0]]=d
for acc,d in seen.items():
    if acc.startswith('GSE'): print('SERIES',acc,d)
    else: print('SAMPLE',acc,{k:v for k,v in d.items() if k in ['Sample_title','Sample_source_name_ch1','Sample_characteristics_ch1','Sample_treatment_protocol_ch1','Sample_growth_protocol_ch1','Sample_description']})
(q/'outputs/holdout-design-fields.json').write_text(json.dumps(seen,indent=2))
a=json.loads((q/'outputs/assets-GSE216665.json').read_text())
for row in a['items']:
    if row['subject']['label'] not in ['GEO_SOFT','GEO_MINIML']:print('ASSET',row)
