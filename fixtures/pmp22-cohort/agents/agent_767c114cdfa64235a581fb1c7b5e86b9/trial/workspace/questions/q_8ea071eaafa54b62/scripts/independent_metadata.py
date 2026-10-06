"""Persist native GEO maps and fetch a schema probe before a full independent assay analysis."""
import json
from pathlib import Path
import subprocess
q=Path(__file__).resolve().parents[1]
o=q/'inputs/independent'
o.mkdir(exist_ok=True)

def cli(args,label):
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True)
    (o/(label+'.stdout')).write_text(p.stdout)
    (o/(label+'.stderr')).write_text(p.stderr)
    p.check_returncode()
    return json.loads(p.stdout)

for ref,bundle in [('GSE123016','bundle_2d08d4f942a01a40ce238fe5'),('GSE159510','bundle_d43aec8f6c5ddb5e647f5a57')]:
    meta=cli(['data','show',bundle],ref+'-metadata')
    samples={}
    for profile in meta.get('profiles',[]):
        for c in profile.get('facts',{}).get('related_source_context',[]):
            if c['kind']=='sample':
                f=c['body']['fields']
                samples[c['native_id']]={k:v for k,v in f.items() if k in ['Sample_title','Sample_treatment_protocol_ch1','Sample_characteristics_ch1','Sample_data_processing','Sample_extract_protocol_ch1','Sample_supplementary_file_1','Sample_organism']}
    (o/(ref+'-sample-map.json')).write_text(json.dumps(samples,indent=2))
    inventory=cli(['data','list','--scope',bundle,'--limit','100'],ref+'-files')
    assert inventory['next_offset'] is None
    (o/(ref+'-files.json')).write_text(json.dumps(inventory,indent=2))
    print(ref,'SAMPLES',len(samples),'FILES',len(inventory['items']))
for asset in ['asset_969014698396e227503caf28f7e9d158','asset_02abf4e0f2e2f83681f73702f1dbe796']:
    result=cli(['fetch',asset,'--question',q.name],asset+'-fetch-r001')
    print('FETCH',asset,json.dumps(result))
