"""Full deposited gene-count analysis, after auditing sample labels and endpoints."""
from pathlib import Path
import json,gzip,re
import pandas as pd,numpy as np
q=Path(__file__).resolve().parents[1];d=q/'inputs/continuation';o=q/'outputs'
files=sorted(d.glob('GSM34847*_*.count.txt.gz'));assert len(files)==6
series=[];mapping=[]
for p in files:
 sid=p.name.split('_')[0];meta=(d/(sid+'.soft')).read_text()
 title=re.search(r'!Sample_title = (.*)',meta).group(1)
 f=pd.read_csv(p,sep='\t');assert f.shape[1]==2
 sample=f.columns[1];values=pd.to_numeric(f.iloc[:,1]);assert (values>=0).all() and (values==values.astype(int)).all()
 group='Nf' if 'Nf' in sample else 'Rx'
 mapping.append({'GSM':sid,'file':p.name,'count_header':sample,'GEO_title':title,'title_matches_count_header':title==sample.removesuffix('.count'),'group_by_header':group,'tissue':re.search(r'!Sample_characteristics_ch1 = tissue: (.*)',meta).group(1),'genotype':re.search(r'!Sample_characteristics_ch1 = genotype/variation: (.*)',meta).group(1)})
 series.append(pd.Series(values.to_numpy(),index=f.iloc[:,0],name=sid))
assert all(s.index.equals(series[0].index) for s in series)
x=pd.concat(series,axis=1);x.index.name='gene';duplicate=int(x.index.duplicated().sum())
# Preserve every source row; duplicate symbols, if present, are not silently summed.
mask=(x>0).all(axis=1);gm=np.exp(np.log(x.loc[mask]).mean(axis=1));sf=x.loc[mask].div(gm,axis=0).median(axis=0);norm=x.div(sf);cpm=x.div(x.sum(axis=0))*1e6
nf=x.columns[:3];rx=x.columns[3:];assert all(v['group_by_header']=='Nf' for v in mapping[:3]) and all(v['group_by_header']=='Rx' for v in mapping[3:])
tab=x.copy();tab.insert(0,'source_row',np.arange(2,len(x)+2))
for c in x:tab[c+'_norm']=norm[c];tab[c+'_cpm']=cpm[c]
tab['mean_Nf']=norm[nf].mean(axis=1);tab['mean_Rx']=norm[rx].mean(axis=1);tab['mean_all']=norm.mean(axis=1)
tab['Rx_over_Nf']=tab.mean_Rx.div(tab.mean_Nf.replace(0,np.nan));tab['log2_Rx_over_Nf']=np.log2(tab.Rx_over_Nf.where(tab.Rx_over_Nf>0));tab['Rx_over_Nf_CPM']=cpm[rx].mean(axis=1).div(cpm[nf].mean(axis=1).replace(0,np.nan))
pair=np.stack([norm[r].div(norm[n].replace(0,np.nan)).to_numpy() for r in rx for n in nf]);tab['pairwise_ratio_min']=np.nanmin(pair,axis=0);tab['pairwise_ratio_max']=np.nanmax(pair,axis=0)
tab.to_csv(o/'runx-rna-all-features.tsv',sep='\t',na_rep='NA')
eligible=tab.loc[tab.mean_all>=20];ranked=eligible.sort_values('log2_Rx_over_Nf');pd.concat([ranked.head(100),ranked.tail(100)]).to_csv(o/'runx-rna-broad-extremes.tsv',sep='\t',na_rep='NA')
log=np.log2(norm.loc[norm.mean(axis=1)>=20]+1);center=log.T-log.T.mean(axis=0);u,s,v=np.linalg.svd(center,full_matrices=False);pca=pd.DataFrame(u[:,:3]*s[:3],index=x.columns,columns=['PC1','PC2','PC3']);pca.to_csv(o/'runx-rna-pca.tsv',sep='\t');log.corr().to_csv(o/'runx-rna-correlations.tsv',sep='\t')
pd.DataFrame(mapping).to_csv(o/'runx-rna-sample-audit.tsv',sep='\t',index=False)
sel=['Pmp22','Mbp','Mpz','Egr2','Sox10','Runx1','Runx2','Runx3','Jun'];panel=tab.loc[tab.index.isin(sel)];panel.to_csv(o/'runx-rna-context.tsv',sep='\t',na_rep='NA')
summary={'source':'GSE122774 processed gene counts; bulk tissues, not sorted ATAC cells','n_features':len(x),'duplicated_symbols':duplicate,'all_zero':int((x==0).all(axis=1).sum()),'positive_all_for_size_factors':int(mask.sum()),'size_factors':sf.to_dict(),'library_totals':x.sum().to_dict(),'mapping':mapping,'mapping_caution':'Nf803/Nf809 titles are swapped relative to supplementary filenames and internal headers; Rx1692/Rx1698 likewise. Swaps stay within groups, so unpaired group average unaffected. No animal-level cross-assay matching justified. GEO Rx genotype omits Nf1 while primary paper specifies triple KO.','design_caution':'Three samples/group source-reported, but GEO DRG versus tumor labels differ from paper shorthand tumors/DRG. Tissue/state confounding precludes clean genotype causal inference. No new DE p-values.','normalization':'Median ratio from rows positive in all6; sensitivity to CPM; gene symbols retained without promoter attribution','PCA_variance_fraction':(s*s/(s*s).sum()).tolist(),'context_rows':json.loads(panel.reset_index().to_json(orient='records')),'broad_top_up':ranked.tail(15).index.tolist()[::-1],'broad_top_down':ranked.head(15).index.tolist(),'comparison_to_paper':'Paper Figure5 describes higher P1 but unchanged P2 RNA and lower P2 accessibility. Gene-count file cannot independently reproduce transcript estimates; values here are total gene counts with fresh normalization.'}
(o/'runx-rna-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
print(json.dumps({k:summary[k] for k in ['n_features','duplicated_symbols','all_zero','PCA_variance_fraction','broad_top_up','broad_top_down']},indent=2));print(panel[['Rx_over_Nf','Rx_over_Nf_CPM','pairwise_ratio_min','pairwise_ratio_max']].to_string())
