"""Post-outcome check of erythroid/myelin RNA burden raised by broad residuals.
This is a relative-library diagnostic, not a cell-count estimate.
"""
from pathlib import Path
import json,gzip,hashlib
import pandas as pd
import numpy as np
Q=Path(__file__).resolve().parents[1];P=Q.parent/'q_277f20df4b6b47cc';W=Q.parents[1];O=Q/'outputs'
PAN={'erythroid':['Hba-a1','Hba-a2','Hbb-bs','Hbb-bt','Hbb-b1','Hbb-b2','Alas2','Slc4a1','Gypa','Klf1'],'myelin':['Pmp22','Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'],'antioxidant4':['Nqo1','Hmox1','Gclc','Gclm']}
rows=[];genes=[];sources=[]
for r in json.loads((P/'inputs/upstream/rna-fetch-receipts.json').read_text()):
 h=r['receipt']['blob'];p=W/'blobs/sha256'/h[:2]/h;assert hashlib.sha256(p.read_bytes()).hexdigest()==h;s=r['name'].split('_',1)[1].split('.genes')[0];d=pd.read_csv(p,sep='\t',compression='gzip');d['symbol']=d.gene_id.str.split('_',n=1).str[1];sources.append(h)
 for panel,gg in PAN.items():
  hit=d[d.symbol.isin(gg)];rows.append(dict(sample=s,group=s.split('_')[0],panel=panel,matched_symbols=';'.join(hit.symbol),source_rows=len(hit),TPM_sum=hit.TPM.sum(),percent_source_TPM=100*hit.TPM.sum()/d.TPM.sum(),percent_expected_counts=100*hit.expected_count.sum()/d.expected_count.sum()))
  for _,v in hit.iterrows():genes.append(dict(sample=s,panel=panel,gene=v.symbol,TPM=v.TPM,expected_count=v.expected_count))
f=pd.DataFrame(rows);f.to_csv(O/'RNA-burden-diagnostic.tsv',sep='\t',index=False);pd.DataFrame(genes).to_csv(O/'RNA-burden-source-cells.tsv',sep='\t',index=False)
b=f.groupby(['group','panel']).percent_source_TPM.mean().unstack();loss=(b.loc['WT','erythroid']-b.loc['KO','erythroid'])/100;maxscale=np.log2(1/(1-b.loc['WT','erythroid']/100))
r=dict(posthoc_trigger='Hba-a1 negative broad residual; atlas may omit blood-derived RNA',input_blobs=sources,relative_TPM_percent_groupmeans=b.to_dict(),maximum_uniform_inflation_if_all_WT_erythroid_RNA_removed_log2=float(maxscale),caution='Relative transcript composition; erythroid marker output may change within cells. Upper uniform shift assumes other transcripts fixed and all specified WT RNA disappears; no cell fractions.',answer='Compare computed scale with +2.369 antioxidant score and reference-stable logratio +2.480; cannot identify source cells')
(O/'RNA-burden-summary.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n');print(json.dumps(r,indent=2))
