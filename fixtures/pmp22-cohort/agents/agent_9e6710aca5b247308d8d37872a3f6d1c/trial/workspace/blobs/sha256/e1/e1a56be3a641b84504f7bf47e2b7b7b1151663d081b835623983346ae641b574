"""Compact readout from executed contrasts; no new outcome selection."""
from pathlib import Path
import pandas as pd
Q=Path(__file__).resolve().parents[1]
e=pd.read_csv(Q/'outputs/executed-contrasts.tsv',sep='\t')
p=e.loc[e.variant.eq('primary')&e.pseudocount.eq(.5)]
cols=['series','contrast','endpoint','effect_log2','ci95_low','ci95_high','welch_p','permutation_two_sided_p','loo_min','loo_max','baseline_eligible','statuses_valid']
select=p.loc[p.endpoint.isin(['PMP22','EGR2','SOX10','myelin7','PMP22_minus_EGR2','PMP22_minus_SOX10','PMP22_minus_myelin7','CTGF','CYR61','JUN','ITGA6','DAG1','MKI67']) & (~p.contrast.str.contains('minus_WT')|p.endpoint.eq('PMP22'))]
select[cols].to_csv(Q/'outputs/key-readout.tsv',sep='\t',index=False)
print(select[cols].to_string(index=False))
i=pd.read_csv(Q/'outputs/genotype-stiffness-interactions.tsv',sep='\t')
print('\nINTERACTIONS\n',i.loc[i.pseudocount.eq(.5)&i.endpoint.isin(['PMP22','CTGF','CYR61','JUN'])].to_string(index=False))
m=pd.read_csv(Q/'outputs/panel-measurements.tsv',sep='\t')
print('\nPMP22 INDIVIDUALS\n',m.loc[m.requested.eq('PMP22')].to_string(index=False))
print('\nCOVERAGE ISSUES\n',pd.read_csv(Q/'outputs/panel-coverage.tsv',sep='\t').query('n_matches!=1').to_string(index=False))
