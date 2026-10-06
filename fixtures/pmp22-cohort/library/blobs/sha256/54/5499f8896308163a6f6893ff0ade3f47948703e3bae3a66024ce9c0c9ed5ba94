"""Source annotation inspection only; leave numeric array export columns untouched."""
import csv,gzip,json,os
from pathlib import Path
Q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1';WS=Q.parents[1]
h='1327d696aef274054f77adee2331a90dd2a0d88d7be3ba2bd119ea44598d4aba'
with gzip.open(WS/'blobs/sha256'/h[:2]/h,'rt') as f:print('P5_NATIVE_HEADER',next(f).strip());print('P5_EXAMPLE',next(f).strip())
with (Q/'inputs/public/E-MEXP-3491.matrix.txt').open() as f:
    r=csv.reader(f,delimiter='\t');next(r);next(r);names=[row[0] for row in r]
print('CALCITRIOL_NATIVE_FEATURE_NAMES',names[100:120])
with (Q/'inputs/public/Schwanncellscontrol1-annotation-only.txt').open() as f:
    for line in f:
        if line.startswith('FEATURES'):
            keys=line.rstrip('\n').split('\t');break
    rows=[]
    for raw in csv.reader(f,delimiter='\t'):
        if not raw or raw[0]!='DATA':continue
        d=dict(zip(keys,raw))
        if d['ControlType']=='0':
            rows.append({k:d[k] for k in ['ProbeName','GeneName','SystematicName','Description','accessions']})
print('NATIVE_ANNOTATION_EXAMPLES',rows[:8])
for r in rows:
    if r['GeneName'] in ['Pmp22','Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal']:print('NATIVE_PANEL_ANNOTATION',r)
(Q/'outputs/calcitriol-native-annotation.json').write_text(json.dumps(rows,indent=2))
