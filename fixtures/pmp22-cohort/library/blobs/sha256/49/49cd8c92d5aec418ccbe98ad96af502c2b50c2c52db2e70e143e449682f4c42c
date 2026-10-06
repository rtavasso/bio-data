"""Inspect source fields and native table headers without executing source code."""
import gzip
import json
import os
from pathlib import Path

ws = Path(os.environ['BIO_WORKSPACE'])
q = ws / 'questions/q_ec00fef1019a4c6f'
for name in ['discover-nae1', 'discover-matched']:
    obj = json.loads((q / f'outputs/{name}.json').read_text())
    (q / f'outputs/{name}.pretty.json').write_text(json.dumps(obj, indent=2))
    print(name, json.dumps(obj, indent=2)[:20000])
for label, h in [('sorted_rpkm','1327d696aef274054f77adee2331a90dd2a0d88d7be3ba2bd119ea44598d4aba'),('repair_counts','7f8b8f20b3fd13166075450994acd62bf4bcbc610818f79e917a50856a4247fb')]:
    p = ws / 'blobs/sha256' / h[:2] / h
    with gzip.open(p, 'rt') as f:
        print(label, 'HEADER', next(f).strip())
        print('FIRST ROW', next(f).strip()[:700])
for name in ['GSE137947','GSE138577','GSE177037']:
    obj = json.loads((q/f'outputs/design-{name}.json').read_text())
    items = []
    for profile in obj.get('profiles', []):
        for ctx in profile.get('facts',{}).get('related_source_context',[]):
            fields = ctx.get('body',{}).get('fields',{})
            if fields and not any(k.startswith('Platform_') for k in fields):
                items.append({'locator':{k:v for k,v in ctx.items() if k!='body'},'fields':fields})
    (q/f'outputs/fields-{name}.json').write_text(json.dumps(items, indent=2))
    print(name,'CONTEXTS',len(items))
    for item in items:
        fields=item['fields']
        print({k:v for k,v in fields.items() if k in ['Sample_title','Sample_geo_accession','Sample_characteristics_ch1','Series_overall_design','Series_pubmed_id']})
