"""Inspect SOFT sample design before analysis; preserve literal metadata."""
import json
import pathlib
Q=pathlib.Path(__file__).resolve().parents[1]
D=Q/'inputs'/'primary'
rows=[]
for path in sorted(D.glob('*-samples.soft')):
    sample=None
    series=path.name.split('-')[0]
    with path.open(errors='strict') as f:
        for lineno,line in enumerate(f,1):
            line=line.rstrip('\r\n')
            if line.startswith('^SAMPLE = '):
                sample={'series':series,'sample':line.split(' = ',1)[1],'source':path.name,'line':lineno,'metadata':{}}
                rows.append(sample)
            elif line.startswith('^'):
                sample=None
            elif sample and line.startswith(('!Sample_title =','!Sample_source_name_ch1 =','!Sample_organism_ch1 =','!Sample_characteristics_ch1 =','!Sample_treatment_protocol_ch1 =','!Sample_growth_protocol_ch1 =','!Sample_extract_protocol_ch1 =','!Sample_data_processing =','!Sample_supplementary_file','!Sample_description =','!Sample_platform_id =')):
                key,value=line.split(' = ',1)
                sample['metadata'].setdefault(key,[]).append(value)
(Q/'outputs'/'sample-metadata.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
for r in rows:
    m=r['metadata']
    print(r['series'],r['sample'],r['line'], m.get('!Sample_title'),m.get('!Sample_characteristics_ch1'))
    if r['series']=='GSE165206':
        print(json.dumps(m,indent=2))
print('Sample metadata records',len(rows))
