import json,pathlib,re,hashlib
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
q=pathlib.Path(__file__).resolve().parents[1];o=q/'outputs';d=q/'inputs/continuation'
m=json.loads((q/'inputs/continued-reuse.json').read_text());assert hashlib.sha256(pathlib.Path(m['path']).read_bytes()).hexdigest()==m['output_blob']
df=pd.read_parquet(m['path']);cols=['LentiAS-1','LentiAS-2','LentiGFP-1','LentiGFP-2'];hdr=df['#Geneid'].isin(['#Geneid','Geneid']);excluded=df.loc[hdr].to_dict('records');df=df.loc[~hdr].copy();x=df[cols].apply(pd.to_numeric);assert (x>=0).all().all() and (x%1==0).all().all()
pos=(x>0).all(axis=1);sf=x.loc[pos].div(np.exp(np.log(x.loc[pos]).mean(axis=1)),axis=0).median();norm=x.div(sf,axis=1);cpm=x.div(x.sum(),axis=1)*1e6
r=df.copy()
for c in cols:r['norm_'+c]=norm[c];r['cpm_'+c]=cpm[c]
r['mean_norm']=norm.mean(axis=1);r['AS_over_GFP']=norm[cols[:2]].mean(axis=1)/norm[cols[2:]].mean(axis=1);r['log2_AS_over_GFP']=np.log2(r.AS_over_GFP);r['CPM_log2_AS_over_GFP']=np.log2(cpm[cols[:2]].mean(axis=1)/cpm[cols[2:]].mean(axis=1))
pairs=np.stack([np.log2((norm[a]+.5)/(norm[b]+.5)) for a in cols[:2] for b in cols[2:]],axis=1)
r['pairwise_min_log2_pseudocount_0.5']=pairs.min(axis=1);r['pairwise_max_log2_pseudocount_0.5']=pairs.max(axis=1);r['all_pairs_same_direction']=(pairs.min(axis=1)>0)|(pairs.max(axis=1)<0)
r.replace([np.inf,-np.inf],np.nan).to_csv(o/'rna-all-features.tsv',sep='\t',index=False,na_rep='NA')
elig=r.mean_norm>=20;top=r.loc[elig & r.all_pairs_same_direction].assign(abs_effect=lambda x:x.log2_AS_over_GFP.abs()).sort_values('abs_effect',ascending=False);top.head(100).to_csv(o/'rna-broad-extremes.tsv',sep='\t',index=False)
y=np.log2(norm.loc[elig]+1);cor=y.corr();cor.to_csv(o/'rna-sample-correlations.tsv',sep='\t')
# PCA across filtered genes, mean centered without per-gene variance scaling.
z=y.T.to_numpy();z-=z.mean(axis=0);u,s,v=np.linalg.svd(z,full_matrices=False);pcs=u*s;pv=s*s/(s*s).sum();pd.DataFrame(pcs[:,:3],index=cols,columns=['PC1','PC2','PC3']).to_csv(o/'rna-pca.tsv',sep='\t')
fig,ax=plt.subplots(1,2,figsize=(12,4.5));ax[0].scatter(pcs[:2,0],pcs[:2,1],label='AS');ax[0].scatter(pcs[2:,0],pcs[2:,1],label='GFP');
for i,c in enumerate(cols):ax[0].annotate(c,(pcs[i,0],pcs[i,1]),fontsize=8)
ax[0].set(xlabel=f'PC1 ({pv[0]:.1%})',ylabel=f'PC2 ({pv[1]:.1%})',title='RNA library structure');ax[0].legend()
ax[1].scatter(np.log2(r.loc[elig,'mean_norm']+1),r.loc[elig,'log2_AS_over_GFP'],s=3,alpha=.2)
for gene in ['Pmp22','Egr2','Jun','Sox10','Mpz','Mtor','G3bp1']:
 a=r[r['#Geneid']==gene].iloc[0];ax[1].annotate(gene,(np.log2(a.mean_norm+1),a.log2_AS_over_GFP),fontsize=8,color='darkred')
ax[1].axhline(0,c='black',lw=.5);ax[1].set(xlabel='log2 mean normalized count + 1',ylabel='log2 AS/GFP',title='All genes with mean normalized count ≥20');fig.tight_layout();fig.savefig(o/'rna-qc.png',dpi=170);plt.close(fig)
soft=(d/'GSE201623.soft').read_text();records=[]
for block in soft.split('^SAMPLE = ')[1:]:
 lines=block.splitlines();fields={}
 for line in lines[1:]:
  if line.startswith('!Sample_') and ' = ' in line:
   k,val=line.split(' = ',1);fields.setdefault(k,[]).append(val)
 title=fields['!Sample_title'][0];label=title.split(' [')[0].replace(' ','-')
 records.append({'accession':lines[0], 'table_column':label,**{k.replace('!Sample_',''):v for k,v in fields.items() if any(t in k for t in ['title','characteristics','growth_protocol','treatment_protocol','extract_protocol','data_processing','relation'])}})
(d/'rna-sample-audit.json').write_text(json.dumps(records,indent=2,allow_nan=False))
summary={'inherited_representation':m['id'],'input_sha256':m['output_blob'],'excluded_headers':excluded,'rows':len(r),'unique_symbols':r['#Geneid'].nunique(),'duplicate_symbols':r.loc[r['#Geneid'].duplicated(False),'#Geneid'].tolist(),'zero_all_samples':int((x.sum(axis=1)==0).sum()),'fraction_integer_counts':1.0,'library_sums':x.sum().to_dict(),'size_factors':sf.to_dict(),'QC_filter':'mean median-ratio-normalized count >=20','QC_features':int(elig.sum()),'PCA_variance':pv.tolist(),'same_direction_all_pairs_features':int((elig&r.all_pairs_same_direction).sum()),'no_inference_reason':'Two libraries per condition, GEO calls biological replicates but animal/pool/culture-batch identities unspecified. Gene-wise results descriptive; no differential significance or donor-level inference. Correlation does not prove identity.','mapping':'Column order agrees with GEO labels and embedded header. Do not invert groups to match hypothesis.','endpoint':'48h lentivirus gene-level steady-state counts, not nascent RNA, promoter output or protein activity.','zero_semantics':'Observed zero counts kept; ratio with zero denominator written NA, not zero. Pairwise sensitivity uses explicit 0.5 normalized-count pseudocount.','comparison_genes':r.loc[r['#Geneid'].isin(['Pmp22','Egr2','Jun','Sox10','Mpz','Mtor','G3bp1']),['#Geneid','__source_row','AS_over_GFP','log2_AS_over_GFP','CPM_log2_AS_over_GFP','pairwise_min_log2_pseudocount_0.5','pairwise_max_log2_pseudocount_0.5']].to_dict('records')}
(o/'rna-audit-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2));print(cor);print(top[['#Geneid','description','log2_AS_over_GFP']].head(35).to_string(index=False))
