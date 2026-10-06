"""Create compact auditable design fields from managed primary metadata."""
import json
import os
from pathlib import Path
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_ec00fef1019a4c6f'
obj=json.loads((q/'outputs/design-GSE241269.json').read_text())
items=[]
for profile in obj['profiles']:
    for ctx in profile.get('facts',{}).get('related_source_context',[]):
        f=ctx.get('body',{}).get('fields',{})
        if 'Sample_geo_accession' in f or 'Series_geo_accession' in f:
            items.append({'locator':{k:v for k,v in ctx.items() if k!='body'},'fields':f})
(q/'outputs/fields-GSE241269.json').write_text(json.dumps(items,indent=2))
for item in items:
    f=item['fields']
    print({k:v for k,v in f.items() if k in ['Sample_title','Sample_characteristics_ch1','Sample_geo_accession','Sample_description','Sample_extract_protocol_ch1','Sample_data_processing','Series_overall_design']})
