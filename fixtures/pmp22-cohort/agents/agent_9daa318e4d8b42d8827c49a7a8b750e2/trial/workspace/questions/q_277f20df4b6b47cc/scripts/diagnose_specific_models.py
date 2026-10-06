from pathlib import Path
import json
import numpy as np,pandas as pd
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/specific';L=pd.read_csv(O/'discovery-log2CPM.tsv',sep='\t',index_col=0);markers=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];cand=['Ppp6r1','Gtf2f1','Hck'];M=L.loc[markers].mean().values;y=L.loc['Pmp22'].values;states=np.repeat([0,3,5,7],2);fit=lambda X,y:np.linalg.lstsq(X,y,rcond=None)[0]
B=np.column_stack([np.ones(8),M]);Q2=np.column_stack([B,(M-M.mean())**2]);designs={'linear_myelin':B,'quadratic_myelin':Q2};designs.update({'linear_plus_'+g:np.column_stack([B,L.loc[g]]) for g in cand});designs.update({'quadratic_plus_'+g:np.column_stack([Q2,L.loc[g]]) for g in cand});rows=[];sample=[]
for name,X in designs.items():
 coef=fit(X,y);p=np.zeros(8)
 for st in [0,3,5,7]:
  tr=states!=st;p[~tr]=X[~tr]@fit(X[tr],y[tr])
 rows.append({'model':name,'n_parameters':X.shape[1],'in_sample_R2':1-((y-X@coef)**2).sum()/((y-y.mean())**2).sum(),'LOTO_SSE':((y-p)**2).sum(),'LOTO_RMSE':np.sqrt(((y-p)**2).mean())});sample.extend({'model':name,'sample':s,'day':int(st),'observed':yy,'prediction':pp} for s,st,yy,pp in zip(L.columns,states,y,p))
pd.DataFrame(rows).to_csv(O/'nonlinear-baseline-comparison.tsv',sep='\t',index=False);pd.DataFrame(sample).to_csv(O/'nonlinear-baseline-predictions.tsv',sep='\t',index=False)
# Matched within-study gene changes, from already exposed/inherited raw count columns. New computation, retrospective.
AS=pd.read_csv(Q/'outputs/rna-all-features.tsv',sep='\t').set_index('#Geneid');RX=pd.read_csv(Q/'outputs/runx-rna-all-features.tsv',sep='\t').set_index('gene');datasets=[('inherited_Egr2AS_rat',AS[['LentiAS-1','LentiAS-2','LentiGFP-1','LentiGFP-2']],2),('inherited_Runx_mouse',RX[[c for c in RX if c.startswith('GSM') and '_' not in c]],3)]
lock=json.loads((O/'prediction-r002.json').read_text());models=json.loads(lock['prediction'])['frozen_models'];b0=json.loads(lock['baseline_model'])['coefficients'][1];out=[];panel=[]
for name,C,n in datasets:
 if 'Runx' in name:C=C.iloc[:,[3,4,5,0,1,2]] # Rx KO minus Nf control; metadata audited in inherited source
 assert C.shape[1]==2*n
 log=np.log2(C.div(C.sum())*1e6+.5);delta=log.iloc[:,:n].mean(1)-log.iloc[:,n:].mean(1);dy=delta.loc['Pmp22'];dm=delta.loc[markers].mean();base=b0*dm
 for g in markers+cand+['Pmp22','Egr2','Sox10','Jun','Runx1','Runx3']:
  if g in delta:panel.append({'dataset':name,'gene':g,'log2FC':delta.loc[g]})
 for r in models:
  g=r['gene'];dx=delta.loc[g];pred=r['myelin_beta']*dm+r['gene_beta']*dx;out.append({'dataset':name,'mode':'retrospective_exposed','candidate':g,'delta_Pmp22':dy,'delta_myelin':dm,'delta_candidate':dx,'Pmp22_minus_myelin_contrast':dy-dm,'baseline_prediction':base,'augmented_prediction':pred,'SSE_ratio':(dy-pred)**2/(dy-base)**2})
pd.DataFrame(out).to_csv(O/'inherited-retrospective-transfer.tsv',sep='\t',index=False);pd.DataFrame(panel).to_csv(O/'inherited-retrospective-panel.tsv',sep='\t',index=False)
# Baseline-free proportionality residual y - mean markers is directly interpretable, though no causal specificity.
A=pd.read_csv(O/'zeb2-log2-expression.tsv',sep='\t',index_col=0);dy=A.loc['Pmp22'].iloc[:3].mean()-A.loc['Pmp22'].iloc[3:].mean();dm=A.loc[markers].iloc[:,:3].mean().mean()-A.loc[markers].iloc[:,3:].mean().mean();summary={'models':rows,'Zeb2_Pmp22_relative_to_myelin_log2':dy-dm,'retrospective_results':out,'interpretation':'Nonlinear/alternative baseline analysis exploratory; candidate selection and validation unchanged. General injury program adjustment does not isolate causal regulation. Existing sample outcomes were exposed, so inherited contrasts are retrospective.'};(O/'model-diagnostics-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(pd.DataFrame(rows).to_string(index=False));print(pd.DataFrame(out).to_string(index=False))
