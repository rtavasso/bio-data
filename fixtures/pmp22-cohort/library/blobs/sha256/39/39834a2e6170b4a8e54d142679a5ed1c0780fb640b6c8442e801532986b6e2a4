"""Exploratory all-gene residual prediction; never uses validation measurements."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
from scipy.stats import pearsonr
Q=Path(__file__).resolve().parents[1];O=Q/'outputs/specific';W=Q.parents[1]
def blob(h):return W/'blobs/sha256'/h[:2]/h
receipt=json.loads((Q/'inputs/specific/fetch-discovery.json').read_text());raw=pd.read_csv(blob(receipt['blob']),compression='gzip',sep='\t',index_col=0)
# RSEM expected counts can be fractional. Source row labels geneID_geneSymbol; use suffix only for unambiguous equal repeated symbol labels.
parts=[s.split('_') for s in raw.index];ok=[len(p)==2 and p[0]==p[1] for p in parts]
mapping=pd.DataFrame({'source_id':raw.index,'symbol':[p[-1] for p in parts],'unambiguous_repeated_symbol':ok});mapping.to_csv(O/'discovery-feature-map.tsv',sep='\t',index=False)
x=raw.loc[ok].copy();x.index=[p[-1] for p,k in zip(parts,ok) if k];assert not x.index.duplicated().any();assert (x.values>=0).all()
cols=['IL6172','IL6173','IL6176','IL6177','IL6180','IL6181','IL6184','IL6185'];states=np.repeat([0,3,5,7],2);a=x[cols];cpm=a.div(a.sum())*1e6;log=np.log2(cpm+.5)
markers=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];assert set(markers+['Pmp22'])<=set(x.index)
M=log.loc[markers].mean().values;y=log.loc['Pmp22'].values;B=np.column_stack([np.ones(8),M]);fit=lambda X,y:np.linalg.lstsq(X,y,rcond=None)[0]
b=fit(B,y);yr=y-B@b;Y=log.T.values;xr=Y-B@fit(B,Y);den=np.sqrt((xr*xr).sum(0)*(yr*yr).sum());r=(xr*yr[:,None]).sum(0)/np.where(den>1e-12,den,np.nan)
base_cv=np.zeros(8);full_cv=np.zeros((8,len(x)));signs=[]
for state in np.unique(states):
 train=states!=state;test=~train;bt=B[train];base_cv[test]=B[test]@fit(bt,y[train]);xty=Y[train]-bt@fit(bt,Y[train]);yty=y[train]-bt@fit(bt,y[train]);beta=(xty*yty[:,None]).sum(0)/np.maximum((xty*xty).sum(0),1e-12)
 # Fit y = intercept + M coefficient + gene coefficient, and predict held-out state.
 intercept_slope=fit(bt,y[train,None]-Y[train]*beta);full_cv[test]=B[test]@intercept_slope+Y[test]*beta;signs.append(np.sign(beta))
base_sse=float(((y-base_cv)**2).sum());sse=((y[:,None]-full_cv)**2).sum(0)
beta=(xr*yr[:,None]).sum(0)/np.maximum((xr*xr).sum(0),1e-12);coefs=fit(B,y[:,None]-Y*beta)
# Regulatory annotation comes solely from inherited source descriptions, not outcomes in validation.
reuse=json.loads((Q/'inputs/specific/reuse-show.json').read_text());ann=pd.read_parquet(blob(reuse['output_blob']));desc=ann.set_index('#Geneid')['description'].to_dict()
pattern=r'transcription|zinc finger|homeobox|chromatin|histone|polycomb|helicase|RNA.binding|kinase|phosphatase|receptor|methyltransferase|acetyltransferase|deacetylase|ubiquitin.*ligase'
res=pd.DataFrame({'gene':x.index,'description':[desc.get(g,'') for g in x.index],'min_CPM':cpm.min(1).values,'sd_log2CPM':log.std(axis=1).values,'partial_r':r,'gene_beta':beta,'intercept':coefs[0],'myelin_beta':coefs[1],'LOTO_SSE':sse,'LOTO_SSE_over_baseline':sse/base_sse,'LOTO_sign_consistent':(np.array(signs)==np.sign(beta)).all(0)})
res['regulatory_annotation']=res.description.str.contains(pattern,case=False,regex=True,na=False);res['eligible']=(res.min_CPM>=1)&(res.sd_log2CPM>=.25)&~res.gene.isin(markers+['Pmp22'])
res['selection_pass']=res.eligible & res.regulatory_annotation & res.LOTO_sign_consistent & (res.LOTO_SSE_over_baseline<.8)
res=res.sort_values(['LOTO_SSE_over_baseline','gene']);res.to_csv(O/'discovery-all-gene-screen.tsv',sep='\t',index=False,na_rep='NA');selected=res[res.selection_pass].head(3).copy();selected.to_csv(O/'discovery-selected.tsv',sep='\t',index=False)
# Full time adjustment only leaves replicate-level information; descriptive robustness, no pseudo independence.
T=np.eye(4)[np.searchsorted([0,3,5,7],states)];C=np.column_stack([T,M]);yrt=y-C@fit(C,y);xrt=Y-C@fit(C,Y);rt=(xrt*yrt[:,None]).sum(0)/np.maximum(np.sqrt((xrt*xrt).sum(0)*(yrt*yrt).sum()),1e-12)
res['partial_r_adjust_time']=res.gene.map(dict(zip(x.index,rt)));res.to_csv(O/'discovery-all-gene-screen.tsv',sep='\t',index=False,na_rep='NA')
sample=pd.DataFrame({'sample':cols,'day':states,'myelin_score':M,'Pmp22_log2CPM':y,'baseline_fitted':B@b,'Pmp22_residual':yr,'baseline_LOTO_prediction':base_cv});sample.to_csv(O/'discovery-samples.tsv',sep='\t',index=False)
log.to_csv(O/'discovery-log2CPM.tsv',sep='\t');raw.to_csv(O/'discovery-source-counts.tsv',sep='\t')
summary={'source':'GSE177037','input_blob':receipt['blob'],'raw_feature_count':len(raw),'unambiguous_symbol_features':len(x),'ambiguous_features_excluded':int((~np.array(ok)).sum()),'n_purified_samples':8,'sample_unit':'two pooled nerve preparations per state; minimum 10 nerves/sample per GEO; individual nerves not replicates','units':'RSEM expected counts, fractional values retained; CPM with +0.5 before log2','markers':markers,'baseline_coefficients':b.tolist(),'baseline_R2':float(1-(yr@yr)/((y-y.mean())@(y-y.mean()))),'baseline_LOTO_SSE':base_sse,'eligible_all_genes':int(res.eligible.sum()),'eligible_regulatory_annotation':int((res.eligible&res.regulatory_annotation).sum()),'passing_regulatory_candidates':int(res.selection_pass.sum()),'selected':selected.to_dict(orient='records'),'selection':'Top 3 regulatory-description genes by leave-one-timepoint-out SSE; CPM>=1 in all8; SD>=0.25; consistent slope sign in all4 folds; SSE<0.8*baseline. This CV is used for selection and is NOT unbiased validation. Whole feature screen preserved.','limits':'Small n and four states; observational predictors are not causal regulators. Matched-symbol transfer to mouse is a hypothesis. No discovery p-values used to claim significance.'}
(O/'discovery-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2,allow_nan=False))
