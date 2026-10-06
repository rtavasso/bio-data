"""Diagnose distinct constituent exports; do not silently substitute one for another."""
import json
from pathlib import Path
import numpy as np
import openpyxl
import pandas as pd

R=Path(__file__).resolve().parents[1]
S=R/'inputs'/'sources'
OUT=R/'outputs'
w=openpyxl.load_workbook(S/'elife05033s001.xlsx',read_only=True,data_only=False)
rows=list(w.active.iter_rows(values_only=True))
a=pd.DataFrame(rows[2:],columns=['feature']+list(rows[1][1:])).dropna(subset=['feature']).set_index('feature')
b=pd.read_csv(OUT/'GSE65778-full-native-counts.tsv.gz',sep='\t',index_col=0)
lengths=pd.read_csv(OUT/'GSE65778-full-native-lengths.tsv.gz',sep='\t',index_col=0)
report={'native_union':len(b),'source_rows':len(a),'source_unique_genes':a.gene.nunique(),'common_all_libraries':int(b.notna().all(axis=1).sum()),'comparisons':[]}
for c in b:
    sc=c if c.startswith('ribo_') else c.removeprefix('mrna_')+'_hek'
    z=pd.DataFrame({'source':pd.to_numeric(a[sc]),'native':b.loc[a.index,c],'source_length':pd.to_numeric(a['size']),'native_length':lengths.loc[a.index,c]})
    z['ratio']=z.source/z.native.replace(0,np.nan)
    good=(z.source>0)&(z.native>0)
    report['comparisons'].append({'sample':c,'mismatches':int((~np.isclose(z.source,z.native,equal_nan=True)).sum()),'length_mismatches':int((~np.isclose(z.source_length,z.native_length,equal_nan=True)).sum()),'ratio_quantiles':z.loc[good,'ratio'].quantile([0,.25,.5,.75,1]).to_dict(),'first_five':z.iloc[:5].reset_index().to_dict('records'),'target':z.loc[a.gene=='PMP22'].reset_index().to_dict('records')})
report['target_rows']=a.loc[a.gene=='PMP22'].reset_index().to_dict('records')
def clean(value):
    if isinstance(value,dict):
        return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list):
        return [clean(v) for v in value]
    if isinstance(value,(float,np.floating)):
        return float(value) if np.isfinite(value) else None
    return value
report=clean(report)
# This inspection may expose target values but occurs after the frozen prediction.
(OUT/'GSE65778-source-export-discrepancy.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
print(json.dumps(report,indent=2))
