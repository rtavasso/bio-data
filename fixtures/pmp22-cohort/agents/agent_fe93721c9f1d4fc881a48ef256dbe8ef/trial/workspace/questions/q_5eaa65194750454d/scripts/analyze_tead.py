"""Parse only numeric Prism XML tables; ignore serialized Template completely."""
import hashlib
import json
from pathlib import Path
from defusedxml import ElementTree as ET
import numpy as np
import pandas as pd
from scipy import stats
Q=Path(__file__).resolve().parents[1]
ns={'p':'http://graphpad.com/prism/Prism.htm'}
rows=[]
results=[]
for marker in ['Krox20','MPZ','MBP','Oct6']:
    p=Q/f'inputs/tead-numeric/{marker} prism file.pzfx'
    root=ET.fromstring(p.read_bytes())
    tables=root.findall('p:Table',ns)
    assert len(tables)==1
    cols={}
    for column in tables[0].findall('p:YColumn',ns):
        title=column.find('p:Title',ns).text.strip()
        cells=column.findall('p:Subcolumn/p:d',ns)
        assert len(column.findall('p:Subcolumn',ns))==1
        vals=[float(d.text) for d in cells]
        assert len(vals)==3 and all(v>0 for v in vals)
        cols[title]=np.array(vals)
        rows.extend({'endpoint':marker,'group':title,'source_row':i+1,'relative_protein':v,'file_sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for i,v in enumerate(vals))
    assert set(cols)=={'WT','cKO'}
    a,b=np.log2(cols['WT']),np.log2(cols['cKO'])
    delta=float(b.mean()-a.mean())
    va,vb=a.var(ddof=1)/len(a),b.var(ddof=1)/len(b)
    se=float(np.sqrt(va+vb))
    df=float((va+vb)**2/(va**2/(len(a)-1)+vb**2/(len(b)-1)))
    half=float(stats.t.ppf(.975,df)*se)
    r={'endpoint':marker,'log2_change':delta,'geometric_fold':float(2**delta),'ci95_log2':[delta-half,delta+half],
       'n_per_group':3,'source_values':{k:v.tolist() for k,v in cols.items()},
       'source_file':p.name,'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
       'assay':'source quantified Western protein, actin-normalized and relative WT; P50 nerve per Figure4A',
       'unit_limit':'three source mice per genotype; no animal IDs for cross-protein pairing; no RNA/activity/half-life inference; not new densitometry'}
    results.append(r)
    print(json.dumps(r))
(Q/'outputs/tead-protein-contrasts.json').write_text(json.dumps({'results':results,'safety':'Only XML Table numeric cells parsed; Template ignored','source':'PMC10959528 Figure4A source data1'},indent=2,allow_nan=False)+'\n')
pd.DataFrame(rows).to_csv(Q/'outputs/tead-protein-source-values.tsv',sep='\t',index=False)
