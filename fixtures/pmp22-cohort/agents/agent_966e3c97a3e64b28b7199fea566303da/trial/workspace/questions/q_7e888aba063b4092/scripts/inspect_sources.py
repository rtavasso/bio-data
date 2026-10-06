"""Inspect metadata and native headers without executing external material."""
import gzip
import json
import sys
from pathlib import Path
from defusedxml import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
for arg in sys.argv[1:]:
    p=Path(arg)
    if p.suffix=='.soft':
        keep=[]
        seen=set()
        for i,line in enumerate(p.read_text().splitlines(),1):
            if line.startswith(('^SAMPLE','!Series_title','!Series_summary','!Series_overall_design','!Series_pubmed','!Sample_title','!Sample_characteristics','!Sample_treatment','!Sample_extract','!Sample_data_processing','!Sample_data_row_count')):
                if line not in seen or line.startswith(('^SAMPLE','!Sample_title','!Sample_characteristics')):
                    keep.append(f'{i}: {line}')
                    seen.add(line)
        text='\n'.join(keep)
    elif p.suffix=='.xml':
        root=ET.parse(p).getroot()
        text='\n'.join(f'P{i} id={e.get("id", "")}: '+''.join(e.itertext()) for i,e in enumerate(root.iter('p'),1))
    elif p.suffix=='.json':
        obj=json.loads(p.read_text())
        if 'resultList' in obj:
            text='\n'.join(json.dumps({k:r.get(k) for k in ['title','id','pmcid','doi','abstractText']}) for r in obj['resultList']['result'])
        else:
            text=json.dumps(obj,indent=2)
    else:
        with (gzip.open(p,'rt') if p.read_bytes()[:2]==b'\x1f\x8b' else p.open()) as f:
            rows=[next(f) for _ in range(5)]
        text=''.join(rows)
    dest=OUT/(p.name+'.inspection.txt')
    dest.write_text(text+'\n')
    print('SAVED',dest,'\n',text[:22000])
