"""Separate identifier absence from genuine numeric disagreement in source exports."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
a=pd.read_csv(OUT/'GSE65778-paper-constituent-counts.tsv.gz',sep='\t',index_col=0)
b=pd.read_csv(OUT/'GSE65778-full-native-counts.tsv.gz',sep='\t',index_col=0)
rows=[]
for col in a:
    native=b.reindex(a.index)[col]
    present=native.notna()
    mismatch=present & ~np.isclose(a[col],native,equal_nan=True)
    rows.append({'library':col,'source_rows':len(a),'absent_exact_identifier':int((~present).sum()),'present_exact_identifier':int(present.sum()),'numeric_disagreement_where_present':int(mismatch.sum()),'mismatching_present_examples':a.index[mismatch].tolist()[:10]})
# Explicitly inspect the versions exposed by the prior audit, without inferring sequence identity.
target=[]
for col in a:
    exact='uc002goj.2' if col.startswith('mrna_') else 'uc002goj.3'
    av=float(a.loc['uc002goj.3',col])
    bv=float(b.loc[exact,col])
    assert av==bv
    target.append({'library':col,'paper_identifier':'uc002goj.3','native_identifier':exact,'paper_count':av,'native_count':bv,'numeric_agreement':True})
report={'comparisons':rows,'PMP22_explicit_numeric_corroboration':target,'interpretation':'Identifier absence is distinct from disagreement of measured values. Source-paper target RNA values equal native uc002goj.2 RNA values; source-paper target RPF values equal native uc002goj.3 RPF values. This corroborates the deposited constituents, NOT transcript sequence/isoform equivalence and NOT independent replication. The quantitative analysis still uses both assays from the self-contained source table; no version suffix is silently repaired.'}
(OUT/'GSE65778-identifier-numeric-audit.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
print(json.dumps(report,indent=2))
