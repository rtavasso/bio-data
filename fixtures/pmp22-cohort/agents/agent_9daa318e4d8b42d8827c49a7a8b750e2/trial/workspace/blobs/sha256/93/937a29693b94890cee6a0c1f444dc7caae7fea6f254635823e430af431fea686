"""Execute frozen r002 candidate models on independent processed perturbation data."""
from pathlib import Path
import json,gzip,io,itertools
import numpy as np,pandas as pd
Q=Path(__file__).resolve().parents[1];D=Q/'inputs/specific';O=Q/'outputs/specific';W=Q.parents[1]
lock=json.loads((O/'prediction-r002.json').read_text());models=json.loads(lock['prediction'])['frozen_models'];markers=['Mpz','Mbp','Mag','Prx','Plp1','Cnp','Mal'];candidates=[r['gene'] for r in models];b0=json.loads(lock['baseline_model'])['coefficients'][1]
def table(text,start,end):return pd.read_csv(io.StringIO(text.split(start+'\n')[1].split(end)[0]),sep='\t')
soft=(D/'GSM1972986.soft').read_text();assert "#VALUE = Matrix data contains normalized logarithmic (log2) data" in soft
mat=table(gzip.open(D/'GSE76027_series_matrix.txt.gz','rt').read(),'!series_matrix_table_begin','!series_matrix_table_end').set_index('ID_REF')
plat=table((D/'GPL13730.soft').read_text(),'!platform_table_begin','!platform_table_end');gene_info=pd.read_csv(D/'Mus_musculus.gene_info.gz',sep='\t',dtype=str);gene_info=gene_info.loc[gene_info['#tax_id']=='10090'].copy();assert len(gene_info)>0
# Source platform Entrez mapping, authoritative NCBI symbol. Median across unambiguous probes fixed before outcomes.
idmap=gene_info.set_index('GeneID')['Symbol'];plat['symbol']=plat.ENTREZ_GENE_ID.astype(str).map(idmap);mapping=plat[['ID','ENTREZ_GENE_ID','symbol','Description']];mapping.to_csv(O/'validation-array-mapping.tsv',sep='\t',index=False,na_rep='NA')
sym=mat.index.to_series().map(plat.set_index('ID')['symbol']);mapped=mat.assign(symbol=sym);A=mapped.dropna(subset=['symbol']).groupby('symbol').median(numeric_only=True);assert set(markers+candidates+['Pmp22'])<=set(A.index)
A.to_csv(O/'zeb2-log2-expression.tsv',sep='\t');samples=pd.DataFrame({'sample':A.columns,'group':['KO']*3+['Ctrl']*3});samples.to_csv(O/'zeb2-samples.tsv',sep='\t',index=False)
M=A.loc[markers].mean().values;y=A.loc['Pmp22'].values;ko=np.arange(3);ctrl=np.arange(3,6);delta=lambda v:float(v[ko].mean()-v[ctrl].mean());dm=delta(M);dy=delta(y);baseline=b0*dm;B=np.column_stack([np.ones(6),M]);fit=lambda X,y:np.linalg.lstsq(X,y,rcond=None)[0];yr=y-B@fit(B,y);rows=[];pred_rows=[];rng=np.random.default_rng(27722)
resamples=np.array(list(itertools.product(range(3),repeat=3)));pairs=list(itertools.product(resamples,resamples));boot_dy=np.array([y[k].mean()-y[c+3].mean() for k,c in pairs]);boot_dm=np.array([M[k].mean()-M[c+3].mean() for k,c in pairs]);base_se=(dy-baseline)**2
for r in models:
 g=r['gene'];x=A.loc[g].values;dx=delta(x);pred=r['myelin_beta']*dm+r['gene_beta']*dx;err=(dy-pred)**2;xr=x-B@fit(B,x);slope=float((xr@yr)/(xr@xr));partial=float(np.corrcoef(xr,yr)[0,1]);boot_dx=np.array([x[k].mean()-x[c+3].mean() for k,c in pairs]);boot_pred=r['myelin_beta']*boot_dm+r['gene_beta']*boot_dx;diff=(boot_dy-boot_pred)**2-(boot_dy-b0*boot_dm)**2;ci=np.quantile(diff,[.05/3/2,1-.05/3/2]);ratio=err/base_se
 status='supported_in_scope' if ratio<=.8 and ci[1]<0 and slope<0 else 'contradicted' if ratio>=1 or slope>=0 else 'unresolved'
 rows.append({'candidate':g,'delta_Pmp22':dy,'delta_myelin':dm,'delta_candidate':dx,'baseline_prediction':baseline,'augmented_prediction':pred,'baseline_squared_error':base_se,'augmented_squared_error':err,'SSE_ratio':ratio,'squared_error_difference':err-base_se,'bootstrap98.333_lo':float(ci[0]),'bootstrap98.333_hi':float(ci[1]),'validation_conditional_slope':slope,'validation_partial_r':partial,'status_under_lock':status})
 pred_rows.append({'context':'Zeb2_DhhCre_P25','candidate':g,'delta_Pmp22':dy,'delta_myelin':dm,'delta_candidate':dx,'baseline_prediction':baseline,'augmented_prediction':pred,'SSE_ratio':ratio,'n_KO':3,'n_control':3})
pd.DataFrame(rows).to_csv(O/'validation-primary-results.tsv',sep='\t',index=False)
# Independent HDAC3 n=1 per group; preserve FPKM ambiguity and only use unique matching rows.
hdac={};qc=[]
for key in ['cnp-ctrl','cnp-ko','dhh-ctrl','dhh-ko']:
 r=json.loads((D/f'fetch-hdac3-{key}.json').read_text());h=r['blob'];f=pd.read_csv(W/'blobs/sha256'/h[:2]/h,compression='gzip',sep='\t');dup=f.gene_short_name.duplicated(keep=False);good=~dup & f.gene_short_name.ne('-');v=f.loc[good].set_index('gene_short_name').FPKM;hdac[key]=v
 qc.append({'sample':key,'source_rows':len(f),'unique_unambiguous_rows':len(v),'duplicate_symbol_rows_excluded':int(dup.sum()),'asset':r['asset_revision'],'panel_status':f.loc[f.gene_short_name.isin(markers+candidates+['Pmp22']),['gene_short_name','FPKM_status']].to_dict(orient='records')})
H=pd.DataFrame(hdac);H.to_csv(O/'hdac3-FPKM.tsv',sep='\t',na_rep='NA');assert H.loc[markers+candidates+['Pmp22']].notna().all().all();lh=np.log2(H+.5)
for cre in ['cnp','dhh']:
 dd=lh[cre+'-ko']-lh[cre+'-ctrl'];dm=float(dd.loc[markers].mean());dy=float(dd.loc['Pmp22']);base=b0*dm
 for r in models:
  g=r['gene'];dx=float(dd.loc[g]);pred=r['myelin_beta']*dm+r['gene_beta']*dx;pred_rows.append({'context':'Hdac3_'+cre+'Cre_P6','candidate':g,'delta_Pmp22':dy,'delta_myelin':dm,'delta_candidate':dx,'baseline_prediction':base,'augmented_prediction':pred,'SSE_ratio':(dy-pred)**2/(dy-base)**2,'n_KO':1,'n_control':1})
pd.DataFrame(pred_rows).to_csv(O/'validation-all-contexts.tsv',sep='\t',index=False)
# All-source array QC and broad effects, with source sample count and donor limitations.
A.corr().to_csv(O/'zeb2-sample-correlations.tsv',sep='\t');center=A.T-A.mean(axis=1);u,ss,v=np.linalg.svd(center.values,full_matrices=False);pd.DataFrame(u[:,:3]*ss[:3],index=A.columns,columns=['PC1','PC2','PC3']).to_csv(O/'zeb2-PCA.tsv',sep='\t');effects=A.iloc[:,:3].mean(1)-A.iloc[:,3:].mean(1);effects.sort_values().to_csv(O/'zeb2-all-gene-effects.tsv',sep='\t',header=['KO_minus_control_log2'])
summary={'lock':'outputs/specific/prediction-r002.json','primary_source':'GSE76027','array_rows':len(mat),'mapped_symbols':len(A),'unmapped_probes':int(sym.isna().sum()),'units_evidence':'inputs/specific/GSM1972986.soft #VALUE explicitly says RMA normalized log2','marker_set':markers,'array_PCA_variance':(ss*ss/(ss*ss).sum()).tolist(),'primary_results':rows,'secondary_results':pred_rows[3:],'hdac3_qc':qc,'inference_limit':'Zeb2 n3 mice/group, small-n discrete bootstrap729 combinations. HDAC3 n1/library per condition, no replicate uncertainty. Cross-species, assay and state transfer; these do not directly perturb selected candidates. Eed r001 remains untestable.'}
(O/'validation-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(pd.DataFrame(rows).to_string(index=False));print(pd.DataFrame(pred_rows).to_string(index=False))
