"""Enumerate RNF40 RNA files and their preserved sample metadata."""
import json
import subprocess
from pathlib import Path
q=Path(__file__).resolve().parents[1]
r=json.loads((q/'outputs/rnf40-geo-resolve.json').read_text())
print('RESOLVE',r)
for name,args in [('rnf40-geo-assets',['data','list','--scope',r['bundle'],'--limit','100']),('rnf40-geo-metadata',['data','show',r['bundle']])]:
    p=subprocess.run(['./bin/bio',*args],capture_output=True,text=True,check=True)
    (q/f'outputs/{name}.json').write_text(p.stdout)
    d=json.loads(p.stdout)
    if name.endswith('assets'):
        print(d)
    else:
        for profile in d['profiles']:
            for record in profile['facts'].get('related_source_context',[]):
                fields=record.get('body',{}).get('fields',{})
                print('SAMPLE', {k:fields.get(k) for k in ['Sample_geo_accession','Sample_title','Sample_characteristics_ch1','Sample_data_processing','Sample_extract_protocol_ch1','Sample_supplementary_file']})
