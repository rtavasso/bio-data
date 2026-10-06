import pandas as pd,numpy as np,json,pathlib
q=pathlib.Path(__file__).resolve().parents[1]
m=json.loads((q/'inputs/artifact_ae47d75299e31396b253c089db31ef6a95911ffab74697818aa7dcda5135160a.json').read_text())
df=pd.read_parquet(m['path'])
print(df.columns.tolist())
cols=['LentiAS-1','LentiAS-2','LentiGFP-1','LentiGFP-2']
headers=df['#Geneid'].isin(['#Geneid','Geneid']) & df['LentiAS-1'].eq('LentiAS-1')
excluded_headers=df.loc[headers,'__source_row'].tolist()
df=df.loc[~headers].copy()
x=df[cols].apply(pd.to_numeric)
positive=(x>0).all(axis=1)
gm=np.exp(np.log(x.loc[positive]).mean(axis=1))
sf=x.loc[positive].div(gm,axis=0).median()
norm=x.div(sf,axis=1)
panel=['Pmp22','Egr2','Sox10','Jun','Junb','Jund','Ezh2','Wdr5','Yy1','Erbb2','Erbb3','Mtor','Tead1','Yap1','Wwtr1','Pou3f1','Mpz','Mbp','Ngfr','Gfap','Shh','Bdnf','Ddit3','Hspa5','Abca1','Srebf2','Canx','Rer1']
out=df[df['#Geneid'].isin(panel)].copy()
for c in cols: out[c+'_median_ratio_normalized']=norm.loc[out.index,c]
out['descriptive_AS_over_GFP']=norm.loc[out.index,cols[:2]].mean(axis=1)/norm.loc[out.index,cols[2:]].mean(axis=1)
out['descriptive_log2_AS_over_GFP']=np.log2(out['descriptive_AS_over_GFP'])
out.to_csv(q/'outputs/egr2-as-regulatory-panel.tsv',sep='\t',index=False)
meta={'input_artifact':m['id'],'input_blob':m['output_blob'],'excluded_repeated_header_source_rows':excluded_headers,'feature_rows':len(df),'positive_in_all_samples':int(positive.sum()),'size_factors':sf.to_dict(),'library_sums':x.sum().to_dict(),'missing_panel_genes':sorted(set(panel)-set(out['#Geneid'])),'method':'Median count/geometric-mean ratio per sample, using genes positive in all four samples; descriptive group means only, no p-values or donor independence inference. Gene-level counts are not promoter output; no pseudocount.','panel':panel}
(q/'outputs/rna-normalization.json').write_text(json.dumps(meta,indent=2))
print(out[['#Geneid']+cols+['descriptive_AS_over_GFP']].to_string(index=False))
