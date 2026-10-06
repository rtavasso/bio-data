"""Inspect source sample identities and native matrix identifiers, not derived effects."""
import gzip,json,os
from pathlib import Path
ws=Path(os.environ['BIO_WORKSPACE']);q=ws/'questions/q_6a3a0a07fa5d4da1'
x=json.loads((q/'outputs/repair-source-current.json').read_text())
fields={}
for p in x['profiles']:
    f=p.get('facts',{})
    if f.get('source_record'): print('SOURCE_RECORD',f['source_record'])
    for a in f.get('related_source_context',[]):
        d=a.get('body',{}).get('fields',{})
        if d: fields[(d.get('Sample_geo_accession') or d.get('Series_geo_accession') or [a.get('native_id','')])[0]]=d
(q/'outputs/fields-GSE177037-full.json').write_text(json.dumps(fields,indent=2))
for acc,d in fields.items(): print(acc,{k:v for k,v in d.items() if k in ['Sample_title','Sample_description','Sample_characteristics_ch1','Sample_data_processing','Sample_supplementary_file','Series_title','Series_summary','Series_overall_design']})
for p in sorted((q/'outputs').glob('fetch-NRG1-*.json')):
    x=json.loads(p.read_text());print(p.name,x)
    if x.get('blob'):
        h=x['blob'];f=ws/'blobs/sha256'/h[:2]/h
        with gzip.open(f,'rt') as stream:
            print('FIRST_ROWS',[next(stream).strip() for _ in range(4)])
