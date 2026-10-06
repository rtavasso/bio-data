"""Post-validation platform/context diagnostic; summary FPKM not independent replicate matrix."""
from pathlib import Path
import json,openpyxl
import numpy as np,pandas as pd
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/specific';D=Q/'inputs/specific';r=json.loads((D/'fetch-zeb2-rnaseq-diff.json').read_text());h=r['blob'];p=Q.parents[1]/'blobs/sha256'/h[:2]/h
with p.open('rb') as f:
 w=openpyxl.load_workbook(f,read_only=True,data_only=False);sheet=w.worksheets[0];rows=list(sheet.iter_rows(values_only=True));assert not any(isinstance(v,str) and v.startswith('=') for row in rows for v in row);T=pd.DataFrame(rows[1:],columns=rows[0])
assert T.test_id.is_unique;T=T.set_index('test_id');assert set(T.sample_1.dropna())=={'WT'} and set(T.sample_2.dropna())=={'Sip1cKOc'}
markers=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];cand=['Ppp6r1','Gtf2f1','Hck'];selected=markers+cand+['Pmp22','Egr2','Sox10','Jun','Zeb2'];panel=T.loc[selected].copy();panel['source_row']=[list(T.index).index(g)+2 for g in selected];panel['eligible_for_quantitative_diagnostic']=panel.status.eq('OK') & panel.value_1.notna() & panel.value_2.notna();panel['calculated_log2_change']=np.log2((pd.to_numeric(panel.value_2)+.5)/(pd.to_numeric(panel.value_1)+.5)).where(panel.eligible_for_quantitative_diagnostic);panel.to_csv(O/'zeb2-rnaseq-native-panel.tsv',sep='\t',na_rep='NA')
# Verify author's column label literally says ln; recomputed endpoint explicitly log2.
positive=T.status.eq('OK') & (pd.to_numeric(T.value_1)>0) & (pd.to_numeric(T.value_2)>0);valid=T.loc[positive].copy();ln=np.log(pd.to_numeric(valid.value_2)/pd.to_numeric(valid.value_1));given=pd.to_numeric(valid['ln(fold_change)']);lnerr=float(np.median(abs(ln-given)));log2err=float(np.median(abs(ln/np.log(2)-given)))
L=pd.read_csv(O/'discovery-log2CPM.tsv',sep='\t',index_col=0);res=[];fit=lambda X,y:np.linalg.lstsq(X,y,rcond=None)[0]
for label,ms in [('full7',markers),('omit_Mpz',[m for m in markers if m!='Mpz'])]:
 needed=ms+cand+['Pmp22'];elig=bool(panel.loc[needed,'eligible_for_quantitative_diagnostic'].all())
 if not elig:
  res.append({'score':label,'status':'ineligible','reason':'non-OK or missing source panel estimate'});continue
 y=L.loc['Pmp22'].values;M=L.loc[ms].mean().values;B=np.column_stack([np.ones(len(M)),M]);b=fit(B,y);delta=panel.calculated_log2_change;dy=delta.loc['Pmp22'];dm=delta.loc[ms].mean();base=b[1]*dm
 for g in cand:
  coef=fit(np.column_stack([B,L.loc[g].values]),y);pred=coef[1]*dm+coef[2]*delta.loc[g];res.append({'score':label,'candidate':g,'status':'exploratory_only','delta_Pmp22':dy,'delta_myelin':dm,'Pmp22_minus_myelin':dy-dm,'delta_candidate':delta.loc[g],'baseline_prediction':base,'augmented_prediction':pred,'SSE_ratio':(dy-pred)**2/(dy-base)**2})
pd.DataFrame(res).to_csv(O/'zeb2-rnaseq-diagnostic.tsv',sep='\t',index=False,na_rep='NA');summary={'source':'GSE74381; independent P7 Zeb2 P0-Cre? Cre driver must be sourced from paper, not inferred here','source_rows':len(T),'status_counts':T.status.value_counts().to_dict(),'group_summary_only':'Cuffdiff value_1 WT and value_2 Sip1cKOc. GEO describes n2 pooled samples/group, but supplied summary is not four independently inspectable columns; no reconstructed replicates or new uncertainty.','ln_column_median_absolute_error_against_ln':lnerr,'ln_column_median_absolute_error_against_log2':log2err,'results':res,'exposure':'Post-failed Zeb2 P25 primary test, exploratory diagnostic only. General Zeb2 paper phenotype already exposed before acquisition.','limitations':'Different age and Cre/context, gene summary quantification. Cannot isolate array compression from biology. Native failed quantification excluded.'};(O/'zeb2-rnaseq-diagnostic-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(panel[['status','value_1','value_2','calculated_log2_change']].to_string());print(pd.DataFrame(res).to_string(index=False))
