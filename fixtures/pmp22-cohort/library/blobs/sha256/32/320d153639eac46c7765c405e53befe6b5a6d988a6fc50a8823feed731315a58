"""Trace the explicitly cited high-temporal dataset origin and measure array scale only."""
import csv,gzip,json,os
from pathlib import Path
from defusedxml import ElementTree as ET
import numpy as np
q=Path(os.environ['BIO_WORKSPACE'])/'questions/q_6a3a0a07fa5d4da1'
root=ET.parse(q/'inputs/public/PMC5405595.xml').getroot()
for ref in root.iter('ref'):
    if ''.join(ref.find('label').itertext()).strip() in {'12','12.'}: print(ET.tostring(ref,encoding='unicode'))
with gzip.open(q/'inputs/public/GSE163132_series_matrix.txt.gz','rt') as f:
    for line in f:
        if line.startswith('!series_matrix_table_begin'):break
    rows=csv.reader(f,delimiter='\t');header=next(rows);values=[];probes=[]
    for row in rows:
        if row[0].startswith('!'):break
        probes.append(row[0]);values.extend(map(float,row[1:]))
    print('ARRAY_STRUCTURE',len(probes),len(header)-1,'minmax',min(values),max(values),'quantiles',np.quantile(values,[0,.01,.5,.99,1]).tolist(),'duplicates',len(probes)-len(set(probes)))
