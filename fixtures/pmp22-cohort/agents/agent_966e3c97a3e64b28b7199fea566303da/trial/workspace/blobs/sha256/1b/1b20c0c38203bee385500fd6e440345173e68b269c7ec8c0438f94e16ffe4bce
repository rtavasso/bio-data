"""Retrospective GSE90070 paired-fraction reanalysis. No author code or raw reads."""
from pathlib import Path
import json,re,hashlib,itertools,sys,platform
import numpy as np,pandas as pd
from scipy import stats
Q=Path(__file__).resolve().parents[1]; D=Q/'inputs/iteration'; O=Q/'outputs/iteration';W=Q.parents[1]
# Read immutable copies registered before execution; inventory is itself an input.
inv=json.loads((O/'input-objects.json').read_text())
def source(name):
 h=inv[name]['blob'];p=W/'blobs/sha256'/h[:2]/h
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h
 return p
raw=pd.read_csv(source('GSE90070_dataCount.csv.gz'),compression='gzip',index_col=0)
assert raw.index.is_unique and raw.columns.is_unique
assert np.isfinite(raw.to_numpy()).all() and (raw.to_numpy()>=0).all() and (raw.to_numpy()%1==0).all()
records=[]
for b in source('GSE90070-samples.soft').read_text().split('^SAMPLE = ')[1:]:
 def val(k):return re.search(r'^!Sample_'+k+r' = (.*)$',b,re.M)[1].strip()
 title=val('title');condition,fraction,rep=title.rsplit('_',2)
 col=re.search(r'Sample name: (\S+)',b)[1]
 records.append(dict(column=col,gsm=b.splitlines()[0],title=title,condition=condition,fraction=fraction,replicate=int(rep),pair=condition+'_'+rep))
samples=pd.DataFrame(records).set_index('column').loc[raw.columns]
assert len(samples)==32 and set(samples.fraction)=={'In','H'}
for c in samples.condition.unique():
 for rep in range(1,5):assert len(samples[(samples.condition==c)&(samples.replicate==rep)])==2
positive=(raw>0).all(axis=1);gm=np.exp(np.log(raw.loc[positive]).mean(axis=1));sf=raw.loc[positive].div(gm,axis=0).median(axis=0);sf/=np.exp(np.log(sf).mean())
samples['library_sum']=raw.sum();samples['median_ratio_factor']=sf;samples.to_csv(O/'isr-samples.tsv',sep='\t')
norm=raw/sf;log=np.log2(norm+0.5);log.to_csv(O/'isr-log2-normalized.tsv',sep='\t')
# eligibility established independently of observed direction, not source status flags (none supplied).
eligible=(raw>=10).all(axis=1)
def bh(p):
 p=np.asarray(p);out=np.full(len(p),np.nan);ok=np.isfinite(p);v=p[ok];order=np.argsort(v);adj=np.minimum.accumulate((v[order]*len(v)/np.arange(1,len(v)+1))[::-1])[::-1];tmp=np.empty(len(v));tmp[order]=np.minimum(adj,1);out[ok]=tmp;return out
contrasts=[('acute','Tg1','Ctrl'),('chronic_vs_acute','Tg16','Tg1'),('chronic_vs_control','Tg16','Ctrl'),('PERKi','Tg16+PERKi','Tg16')]
# Determine literal conditions rather than silently assuming labels.
print('conditions',samples.condition.unique().tolist());assert set(samples.condition)=={'Ctrl','Tg1','Tg16','Tg16+PERKi'}
allrows=[]
for method,nn in [('median_ratio',norm),('CPM',raw/raw.sum()*1e6)]:
 ll=np.log2(nn.where(nn>0))
 def values(c,f):return ll[samples[(samples.condition==c)&(samples.fraction==f)].sort_values('replicate').index].to_numpy()
 for name,a,b in contrasts:
  ai,ah,bi,bh_=values(a,'In'),values(a,'H'),values(b,'In'),values(b,'H')
  # Fraction pairing is supported by GEO design; cross-treatment pairing is NOT assumed.
  ar,br=ah-ai,bh_-bi
  for endpoint,x,y in [('cytosolic',ai,bi),('polysome',ah,bh_),('relative_loading',ar,br)]:
   effect=np.mean(x,axis=1)-np.mean(y,axis=1);vx=np.var(x,axis=1,ddof=1)/4;vy=np.var(y,axis=1,ddof=1)/4;se=np.sqrt(vx+vy)
   df=(vx+vy)**2/(vx*vx/3+vy*vy/3);delta=stats.t.ppf(.975,df)*se
   with np.errstate(invalid='ignore',divide='ignore'):p=2*stats.t.sf(abs(effect/se),df)
   p[~eligible]=np.nan
   # complete removal of each one replicate from either group, no post-selection tuning
   loo=np.stack([np.mean(np.delete(x,i,axis=1),axis=1)-np.mean(np.delete(y,j,axis=1),axis=1) for i in range(4) for j in range(4)])
   out=pd.DataFrame(dict(gene=raw.index,method=method,contrast=name,endpoint=endpoint,eligible=eligible.to_numpy(),log2_effect=effect,ci_low=effect-delta,ci_high=effect+delta,p_descriptive=p,q_within_contrast_endpoint=bh(p),loo_min=np.min(loo,axis=0),loo_max=np.max(loo,axis=0)))
   out['effect_percentile_eligible']=out.log2_effect.where(eligible.to_numpy()).rank(pct=True)
   allrows.append(out)
res=pd.concat(allrows,ignore_index=True).replace([np.inf,-np.inf],np.nan);res.to_csv(O/'isr-all-effects.tsv',sep='\t',index=False)
panel=['Pmp22','Atf4','Ddit3','Ppp1r15a','Hspa5','Xbp1','Atf6','Eif3d','Eif2ak3','Canx','Uggt1','Abca1','Srebf1','Srebf2','Mpz','Mbp','Sox10','Egr2']
res[res.gene.isin(panel)].to_csv(O/'isr-panel-effects.tsv',sep='\t',index=False)
raw.loc[raw.index.isin(panel)].to_csv(O/'isr-panel-source-counts.tsv',sep='\t')
# Entire eligible universe QC and annotation-independent top departures.
x=log.loc[eligible].to_numpy().T;x-=x.mean(axis=0);u,s,vt=np.linalg.svd(x,full_matrices=False)
pca=samples.copy();pca['PC1']=u[:,0]*s[0];pca['PC2']=u[:,1]*s[1];pca.to_csv(O/'isr-PCA.tsv',sep='\t')
log.loc[eligible].corr().to_csv(O/'isr-sample-correlations.tsv',sep='\t')
sel=res[(res.method=='median_ratio')&res.eligible&(res.endpoint=='relative_loading')].copy();sel['abs_effect']=sel.log2_effect.abs();sel.sort_values('abs_effect',ascending=False).groupby('contrast').head(30).to_csv(O/'isr-broad-loading-extremes.tsv',sep='\t',index=False)
summary={'source_rows':len(raw),'columns':len(raw.columns),'positive_all_samples':int(positive.sum()),'eligible_min10_all32':int(eligible.sum()),'pmp22_min_raw':int(raw.loc['Pmp22'].min()),'zero_cells':int((raw==0).sum().sum()),'PC_variance':(s*s/(s*s).sum())[:4].tolist(),'source_semantics':'Deposited integer gene read counts; no quality/status columns. >=10 in all32 eligibility. Missing genes not zero. H fraction >4 ribosomes; paired with cytosolic from same sample.','units':'Four labelled replicates/condition; source does not document separate donor identities or clearly distinguish biological from technical replicates. Treat inferential intervals/p values as conditional descriptive summaries of replicate variation. No population biological claim.','normalization':'Median ratio using positive-all genes; CPM sensitivity. Neither establishes absolute translation or global translation restoration without external calibration.','analysis':'Welch comparison of within-sample log2 H/Input across conditions; no cross-condition pairing; unmoderated descriptive p and BH within each contrast/endpoint; broad selection retrospective, not independent validation.','context':'MEF; no Schwann transfer, promoter attribution, RNA synthesis versus stability, or direct eIF3d-to-Pmp22 effect identified.','environment':{'python':sys.version,'numpy':np.__version__,'pandas':pd.__version__,'platform':platform.platform()}}
(O/'isr-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2));print(res[(res.gene=='Pmp22')&(res.method=='median_ratio')].to_string(index=False))
