from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/context-audit'
f=pd.read_csv(O/'shared-gene-effects.tsv',sep='\t',index_col=0);cl=pd.read_csv(O/'source-cluster-memberships.tsv',sep='\t',index_col=0);t=pd.read_csv(O/'ridd-source-table-effects.tsv',sep='\t')
# Exact literals only, source parenthetical gene symbols; unresolved aliases preserved.
known={'Heparan-α-glucosaminide N-acetyltransferase (Hgsnat)':'Hgsnat','Scavenger receptor class A, member 3 (Scara3)':'Scara3','PDGF receptor (Pdgfrb)':'Pdgfrb','Peripheral myelin protein (Pmp22)':'Pmp22','Galnt10':'Galnt10'}
sel=t[t.source_decreased_stability=='Yes'].copy();sel['footprint_symbol']=sel.target.map(known);sel['mapping_status']=np.where(sel.footprint_symbol.notna(),'exact_source_symbol','unmapped_source_alias');sel.to_csv(O/'ridd-reference-eligibility.tsv',sep='\t',index=False)
p=f.reindex(sel.footprint_symbol.dropna()).copy();p['baseline10']=(p[['MEF_control','NIH_control']]>=10).all(axis=1);p['primary_eligible']=p.baseline10&p.unfloored_2h;p.to_csv(O/'ridd-footprint-context.tsv',sep='\t',index_label='gene')
base=(f[['MEF_control','NIH_control']]>=10).all(axis=1)&(f.baseline_max_abs_log2distance<=1);late=cl.Late_cluster.reindex(f.index).eq(1);refs=f.loc[base&late].drop(index='Pmp22');rows=[]
for time in ['2h','late8vs7h']:
 for ctxt in ['MEF','NIH']:
  fc=np.log2(refs[f'{ctxt}_{time}'].clip(lower=4)/refs[f'{ctxt}_control'].clip(lower=4));target=float(f.loc['Pmp22',f'{ctxt}_log2FC_{time}']);rows.append(dict(time=time,context=ctxt,n=len(refs),target_log2FC=target,reference_median=float(fc.median()),target_percentile=float((fc<target).mean()),number_reference_lower=int((fc<target).sum()),reference_min=float(fc.min()),reference_max=float(fc.max())))
refs.to_csv(O/'late-cluster-baseline-matched-members.tsv',sep='\t',index_label='gene');pd.DataFrame(rows).to_csv(O/'late-cluster-axis-ranks.tsv',sep='\t',index=False)
s=dict(ridd_exact_symbol_matches=len(p),ridd_unmapped_source_aliases=sel.loc[sel.mapping_status=='unmapped_source_alias','target'].tolist(),ridd_primary_eligible=p.index[p.primary_eligible].tolist(),ridd_excluded=p.index[~p.primary_eligible].tolist(),ridd_values=p.reset_index().replace({np.nan:None}).to_dict(orient='records'),late_cluster_axis_ranks=rows,limits='Reduced posthocRIDDpanel, not a full-panel test or measurement of decay. Program was selected onMEFoutcomes. No causal attribution; all same-study footprint-derived.')
(O/'class-comparison-summary.json').write_text(json.dumps(s,indent=2,allow_nan=False)+'\n');print(json.dumps(s,indent=2,allow_nan=False))
