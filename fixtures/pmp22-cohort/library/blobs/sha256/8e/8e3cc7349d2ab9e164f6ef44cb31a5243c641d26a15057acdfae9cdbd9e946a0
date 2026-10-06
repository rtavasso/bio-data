"""Read primary design paragraphs, source-table structure, and exact acquisition receipt."""
import gzip,json,os,re
from pathlib import Path
from defusedxml import ElementTree as ET
ws=Path(os.environ['BIO_WORKSPACE']);q=ws/'questions/q_6a3a0a07fa5d4da1'
for p in sorted((q/'inputs/public').glob('*.xml')):
    print('\nPAPER',p.name)
    try: root=ET.parse(p).getroot()
    except Exception as e: print('not XML',type(e).__name__);continue
    text=' '.join(root.itertext()); print('ACCESSIONS',sorted(set(re.findall(r'GSE\d+|PRJNA\d+|E-MTAB-\d+',text))))
    els=list(root.iter('text')) if 'bioc' in p.name else list(root.iter('p'))
    selected=[]
    for i,el in enumerate(els):
        t=' '.join(el.itertext())
        if re.search(r'GSE\d+|RNA.seq|RNA seq|microarray|data avail|biological replic|independent culture|sequencing data',t,re.I):
            selected.append({'paragraph':i,'text':t});print(i,t[:3800])
    (q/'outputs'/f'{p.name}-design.json').write_text(json.dumps(selected,indent=2))
for name in ['PMC9405209','PMC5960709']:
    root=ET.parse(q/f'inputs/primary/{name}.xml').getroot()
    print('\nSUPPLEMENTS',name)
    for el in root.iter('supplementary-material'): print(' '.join(el.itertext())[:2000],[(c.tag,c.attrib) for c in el])
receipt=json.loads((q/'outputs/fetch-NRG1-control1.json').read_text());print('FETCH_NRG',json.dumps(receipt))
h='7f8b8f20b3fd13166075450994acd62bf4bcbc610818f79e917a50856a4247fb'
with gzip.open(ws/'blobs/sha256'/h[:2]/h,'rt') as f:
    print('REPAIR_HEADER',next(f).strip());print('REPAIR_EXAMPLE',next(f).strip())
