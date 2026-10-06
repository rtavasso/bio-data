"""Inspect source metadata and primary candidate designs without computing target values."""
import json,os,re
from pathlib import Path
from defusedxml import ElementTree as ET
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
x=json.loads((q/'outputs/design-GSE216665.json').read_text())
seen={}
for p in x['profiles']:
    for a in p.get('facts',{}).get('related_source_context',[]):
        f=a.get('body',{}).get('fields',{})
        label=(f.get('Sample_geo_accession') or f.get('Series_geo_accession') or [a.get('native_id','')])[0]
        if f: seen[label]=f
(q/'outputs/design-GSE216665-fields.json').write_text(json.dumps(seen,indent=2))
for label,f in seen.items():
    keys=['Series_title','Series_summary','Series_overall_design','Series_pubmed_id','Sample_title','Sample_characteristics_ch1','Sample_data_processing','Sample_extract_protocol_ch1']
    print(label,json.dumps({k:f[k] for k in keys if k in f}))
a=json.loads((q/'outputs/assets-GSE216665.json').read_text())
print('ASSETS',a)
for p in (q/'inputs/primary').glob('*.xml'):
    print('\nPAPER',p.name)
    try: root=ET.parse(p).getroot()
    except Exception as e: print(type(e).__name__,str(e));continue
    text=' '.join(root.itertext())
    print('ACCESSIONS',sorted(set(re.findall(r'GSE\d+|PRJNA\d+|E-MTAB-\d+',text))))
    selected=[]
    for i,el in enumerate(root.iter('p')):
        t=' '.join(el.itertext())
        if re.search(r'RNA.seq|RNA seq|microarray|GSE\d+|data avail|biological replic|independent culture',t,re.I):
            selected.append({'paragraph':i,'text':t})
    (q/'outputs'/f'{p.stem}-design-text.json').write_text(json.dumps(selected,indent=2))
    for r in selected: print(r['paragraph'],r['text'][:3500])
