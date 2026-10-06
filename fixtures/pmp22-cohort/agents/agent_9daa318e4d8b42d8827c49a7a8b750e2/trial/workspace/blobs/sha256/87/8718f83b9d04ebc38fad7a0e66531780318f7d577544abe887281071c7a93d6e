from pathlib import Path
import pandas as pd,numpy as np,json
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/specific';L=pd.read_csv(O/'discovery-log2CPM.tsv',sep='\t',index_col=0);A=pd.read_csv(O/'zeb2-log2-expression.tsv',sep='\t',index_col=0);markers=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];cand=['Ppp6r1','Gtf2f1','Hck'];fit=lambda X,y:np.linalg.lstsq(X,y,rcond=None)[0];rows=[]
for name,F in [('discovery',L),('validation',A)]:
 M=F.loc[markers].mean().values;y=F.loc['Pmp22'].values
 for i in range(F.shape[1]):
  keep=np.arange(F.shape[1])!=i;B=np.column_stack([np.ones(keep.sum()),M[keep]]);yr=y[keep]-B@fit(B,y[keep])
  for g in cand:
   xx=F.loc[g].values[keep];xr=xx-B@fit(B,xx);rows.append({'dataset':name,'omitted_sample':F.columns[i],'candidate':g,'partial_slope':float((xr@yr)/(xr@xr)),'partial_r':float(np.corrcoef(xr,yr)[0,1])})
pd.DataFrame(rows).to_csv(O/'sample-leverage.tsv',sep='\t',index=False)
mean=A.iloc[:,3:].mean(1);ranks=mean.rank(pct=True);panel=pd.DataFrame({'mean_control_RMA_log2':mean,'control_expression_percentile':100*ranks,'KO_minus_control_log2':A.iloc[:,:3].mean(1)-mean});panel.loc[markers+cand+['Pmp22','Egr2','Sox10','Jun']].to_csv(O/'array-dynamic-range-panel.tsv',sep='\t')
# Bootstrap raw Pmp22 and program contrast uncertainty; 3 mice/group, not six independent change values.
import itertools
I=list(itertools.product(range(3),repeat=3));M=A.loc[markers].mean().values;y=A.loc['Pmp22'].values;vals=[]
for k in I:
 for c in I:
  kk=np.array(k);cc=np.array(c)+3;dy=y[kk].mean()-y[cc].mean();dm=M[kk].mean()-M[cc].mean();vals.append([dy,dm,dy-dm])
ci=np.quantile(vals,[.025,.975],axis=0);summ={'bootstrap_units':'3 source-reported biological mice/group, independently resampled; litter mapping unknown, small n','contrasts':dict(zip(['Pmp22','myelin','Pmp22_minus_myelin'],[{'lower95':float(lo),'upper95':float(hi)} for lo,hi in zip(ci[0],ci[1])])),'leverage_ranges':pd.DataFrame(rows).groupby(['dataset','candidate']).partial_slope.agg(['min','max']).reset_index().to_dict(orient='records'),'array_caution':'Pmp22 control abundance near upper expression range may be affected by array dynamic range. RMA values alone do not prove saturation; source-matched RNA-seq diagnostic is not a clean calibration because age/Cre differ and representations disagree.'};(O/'robustness-summary.json').write_text(json.dumps(summ,indent=2,allow_nan=False));print(json.dumps(summ,indent=2))
